// SAHA recorder: streams MPU6050 readings from the ESP32 over USB.
//
// Works with genuine MPU6050s and the look-alike chips found on many GY-521
// boards (ours reports chip ID 0x72), because it only uses the raw sensor
// registers. No DMP and no library needed.
// Wiring:  VCC -> 3V3, GND -> GND, SDA -> GPIO 21, SCL -> GPIO 22.
//
// Output, about 50 lines per second (CMI is about 10, so this leaves room to resample):
//   t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz
// ax..az: acceleration in m/s² with gravity included (like CMI acc_*)
// gx..gz: rotation speed in rad/s
// qw..qz: orientation quaternion from a Mahony filter (no compass, so heading drifts)
// Each reading ends in *HH, a checksum the recorder uses to drop garbled lines.
// Lines starting with '#' are status messages.

#include <Wire.h>

const long BAUD = 115200;  // 230400 garbled about 3 in 4 lines on our board
const uint8_t ADDR = 0x68;
const unsigned long PERIOD_US = 20000;  // 50 Hz
const float G = 9.81f;
const float GYRO_COUNTS_PER_DPS = 65.5f;  // ±500 °/s setting

float accCountsPerG = 4096;  // ±8 g setting; measured at startup in case a clone differs
float gyroBias[3] = {0, 0, 0};

// Mahony filter state: q = orientation (sensor to room), Kp = how fast it trusts gravity
float q0 = 1, q1 = 0, q2 = 0, q3 = 0;
float Kp = 1.0f;

unsigned long nextUs;

void fail(const char *msg) {
  while (true) {
    Serial.println(msg);
    delay(2000);
  }
}

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

// The same check as the I2C scanner: does anything answer at ADDR?
bool present() {
  Wire.beginTransmission(ADDR);
  return Wire.endTransmission() == 0;
}

// endTransmission(false) keeps the bus open for the read that follows. Its return
// value is unreliable on the ESP32, so success is judged by the bytes that arrive.
uint8_t readReg(uint8_t reg) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(ADDR, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0xFF;
}

// Read accelerometer and gyro (raw counts) in one go, from register 0x3B
bool readRaw(int16_t acc[3], int16_t gyro[3]) {
  Wire.beginTransmission(ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  if (Wire.requestFrom(ADDR, (uint8_t)14) != 14) return false;
  uint8_t b[14];
  for (int i = 0; i < 14; i++) b[i] = Wire.read();
  for (int i = 0; i < 3; i++) {
    acc[i] = (int16_t)(b[2 * i] << 8 | b[2 * i + 1]);
    gyro[i] = (int16_t)(b[8 + 2 * i] << 8 | b[9 + 2 * i]);  // skips temperature (bytes 6-7)
  }
  return true;
}

// One Mahony step. Gyro in rad/s, accel in any unit (only its direction is used).
void mahony(float gx, float gy, float gz, float ax, float ay, float az, float dt) {
  float n = sqrtf(ax * ax + ay * ay + az * az);
  if (n > 0) {
    ax /= n; ay /= n; az /= n;
    // Where the filter currently thinks "up" is, in the sensor's axes
    float vx = 2 * (q1 * q3 - q0 * q2);
    float vy = 2 * (q0 * q1 + q2 * q3);
    float vz = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3;
    // Nudge the rotation toward what the accelerometer says
    gx += Kp * (ay * vz - az * vy);
    gy += Kp * (az * vx - ax * vz);
    gz += Kp * (ax * vy - ay * vx);
  }
  gx *= 0.5f * dt; gy *= 0.5f * dt; gz *= 0.5f * dt;
  float a = q0, b = q1, c = q2;
  q0 += -b * gx - c * gy - q3 * gz;
  q1 += a * gx + c * gz - q3 * gy;
  q2 += a * gy - b * gz + q3 * gx;
  q3 += a * gz + b * gy - c * gx;
  n = sqrtf(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3);
  q0 /= n; q1 /= n; q2 /= n; q3 /= n;
}

void setup() {
  Serial.begin(BAUD);
  delay(500);
  Wire.begin(21, 22);
  Wire.setClock(100000);  // slow and reliable over loose jumper wires

  if (!present()) fail("# ERROR: MPU6050 not found. Check the wiring.");
  uint8_t id = readReg(0x75);
  Serial.printf("# chip ID 0x%02X (0x68 = genuine MPU6050; others are look-alikes and work too)\n", id);

  if (!writeReg(0x6B, 0x01) ||  // wake up, use the gyro clock
      !writeReg(0x19, 19) ||    // 1000 / (1 + 19) = 50 readings per second
      !writeReg(0x1A, 0x04) ||  // smooth out noise above about 21 Hz
      !writeReg(0x1B, 0x08) ||  // gyro ±500 °/s
      !writeReg(0x1C, 0x10)) {  // accelerometer ±8 g
    fail("# ERROR: could not set up the MPU6050.");
  }
  delay(100);

  // Calibrate: average 2 seconds of readings while the sensor is still
  Serial.println("# Calibrating: keep the sensor flat and still...");
  float accSum[3] = {0, 0, 0}, gyroSum[3] = {0, 0, 0};
  int16_t acc[3], gyro[3];
  int n = 0;
  for (int i = 0; i < 200; i++) {
    if (readRaw(acc, gyro)) {
      for (int k = 0; k < 3; k++) { accSum[k] += acc[k]; gyroSum[k] += gyro[k]; }
      n++;
    }
    delay(10);
  }
  if (n < 100) fail("# ERROR: too many failed readings. Check the wiring.");
  for (int k = 0; k < 3; k++) { accSum[k] /= n; gyroBias[k] = gyroSum[k] / n; }
  float measured = sqrtf(accSum[0] * accSum[0] + accSum[1] * accSum[1] + accSum[2] * accSum[2]);
  if (measured > 1000 && measured < 40000) {
    accCountsPerG = measured;
  } else {
    Serial.println("# WARNING: odd acceleration reading during calibration; using the default scale");
  }
  Serial.printf("# acceleration scale: %.0f counts per g\n", accCountsPerG);

  // Start the filter from the measured tilt, so the first readings are already sensible
  Kp = 10.0f;
  for (int i = 0; i < 300; i++) mahony(0, 0, 0, accSum[0], accSum[1], accSum[2], 0.01f);
  Kp = 1.0f;

  Serial.println("# ready");
  Serial.println("t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz");
  nextUs = micros();
}

void loop() {
  if ((long)(micros() - nextUs) < 0) return;
  nextUs += PERIOD_US;

  int16_t acc[3], gyro[3];
  if (!readRaw(acc, gyro)) return;

  float a[3], g[3];
  for (int k = 0; k < 3; k++) {
    a[k] = acc[k] / accCountsPerG * G;
    g[k] = (gyro[k] - gyroBias[k]) / GYRO_COUNTS_PER_DPS * DEG_TO_RAD;
  }
  mahony(g[0], g[1], g[2], a[0], a[1], a[2], PERIOD_US / 1e6f);

  char line[128];
  snprintf(line, sizeof line, "%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f",
           millis(), a[0], a[1], a[2], g[0], g[1], g[2], q0, q1, q2, q3);
  printWithChecksum(line);
}

// Adds "*HH": a CRC-8 of the line, so the recorder can drop garbled lines
void printWithChecksum(const char *line) {
  uint8_t crc = 0;
  for (const char *p = line; *p; p++) {
    crc ^= *p;
    for (int b = 0; b < 8; b++) crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : crc << 1;
  }
  Serial.printf("%s*%02X\n", line, crc);
}
