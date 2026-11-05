// SAHA recorder: streams BNO085 readings from the ESP32 over USB.
//
// Board:   ESP32-WROOM (Arduino IDE: "ESP32 Dev Module").
// Sensor:  Adafruit BNO085 breakout (product 4754), the same chip family as the
//          CMI Helios watch.
// Library: "Adafruit BNO08x" (Arduino Library Manager).
// Wiring:  STEMMA QT cable: red -> 3V3, black -> GND, blue (SDA) -> GPIO 21,
//          yellow (SCL) -> GPIO 22.
//
// Output, about 100 lines per second:
//   t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz
// ax..az: acceleration in m/s² with gravity included (like CMI acc_*)
// gx..gz: rotation speed in rad/s
// qw..qz: orientation quaternion using the compass (like CMI rot_*)
// Lines starting with '#' are status messages.
//
// The BNO085 is known to be fussy over I2C on the ESP32 (it stretches the
// clock). This sketch uses a slow bus and re-enables the reports if the sensor
// resets. If it still drops out, update the esp32 board package.

#include <Adafruit_BNO08x.h>
#include <Wire.h>

const long BAUD = 230400;
const long REPORT_US = 10000;  // 100 Hz

Adafruit_BNO08x bno08x(-1);  // no reset pin wired
sh2_SensorValue_t value;

float acc[3], gyro[3];
bool haveAcc = false, haveGyro = false;

void fail(const char *msg) {
  while (true) {
    Serial.println(msg);
    delay(2000);
  }
}

void enableReports() {
  if (!bno08x.enableReport(SH2_ACCELEROMETER, REPORT_US) ||
      !bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED, REPORT_US) ||
      !bno08x.enableReport(SH2_ROTATION_VECTOR, REPORT_US)) {
    fail("# ERROR: could not start the sensor reports.");
  }
}

void setup() {
  Serial.begin(BAUD);
  delay(500);
  Wire.begin(21, 22);
  Wire.setClock(100000);
  Wire.setTimeOut(1000);

  if (!bno08x.begin_I2C()) fail("# ERROR: BNO085 not found. Check the cable.");
  enableReports();

  Serial.println("# ready");
  Serial.println("t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz");
}

void loop() {
  if (bno08x.wasReset()) {
    Serial.println("# sensor reset, restarting reports");
    enableReports();
    haveAcc = haveGyro = false;
  }
  if (!bno08x.getSensorEvent(&value)) return;

  switch (value.sensorId) {
    case SH2_ACCELEROMETER:
      acc[0] = value.un.accelerometer.x;
      acc[1] = value.un.accelerometer.y;
      acc[2] = value.un.accelerometer.z;
      haveAcc = true;
      break;
    case SH2_GYROSCOPE_CALIBRATED:
      gyro[0] = value.un.gyroscope.x;
      gyro[1] = value.un.gyroscope.y;
      gyro[2] = value.un.gyroscope.z;
      haveGyro = true;
      break;
    case SH2_ROTATION_VECTOR:
      // One line per orientation reading, with the latest acceleration and gyro
      if (!haveAcc || !haveGyro) break;
      Serial.printf("%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
                    millis(), acc[0], acc[1], acc[2], gyro[0], gyro[1], gyro[2],
                    value.un.rotationVector.real, value.un.rotationVector.i,
                    value.un.rotationVector.j, value.un.rotationVector.k);
      break;
  }
}
