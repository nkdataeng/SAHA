// SAHA recorder: streams MPU6050 readings from the ESP32 over USB.
//
// Library: "MPU6050" by Electronic Cats (Arduino Library Manager).
// Wiring:  VCC -> 3V3, GND -> GND, SDA -> GPIO 21, SCL -> GPIO 22.
//
// Output, 100 lines per second (the DMP's default rate):
//   t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz
// ax..gz are raw sensor counts; scripts/record.py converts them.
// Lines starting with '#' are status messages.

#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"
#include "Wire.h"

const long BAUD = 230400;

MPU6050 mpu;
uint8_t fifoBuffer[64];

void fail(const char *msg) {
  while (true) {
    Serial.println(msg);
    delay(2000);
  }
}

void setup() {
  Serial.begin(BAUD);
  delay(500);
  Wire.begin(21, 22);
  Wire.setClock(400000);

  mpu.initialize();
  if (!mpu.testConnection()) fail("# ERROR: MPU6050 not found. Check the wiring.");
  if (mpu.dmpInitialize() != 0) fail("# ERROR: DMP failed to start.");

  // Calibration assumes the sensor is lying flat, chip side up, and not moving.
  Serial.println("# Calibrating: keep the sensor flat and still...");
  mpu.CalibrateAccel(6);
  mpu.CalibrateGyro(6);
  mpu.setDMPEnabled(true);

  Serial.println("# ready");
  Serial.println("t_ms,ax,ay,az,gx,gy,gz,qw,qx,qy,qz");
}

void loop() {
  if (!mpu.dmpGetCurrentFIFOPacket(fifoBuffer)) return;

  Quaternion q;
  VectorInt16 a, g;
  mpu.dmpGetQuaternion(&q, fifoBuffer);
  mpu.dmpGetAccel(&a, fifoBuffer);
  mpu.dmpGetGyro(&g, fifoBuffer);

  Serial.printf("%lu,%d,%d,%d,%d,%d,%d,%.4f,%.4f,%.4f,%.4f\n",
                millis(), a.x, a.y, a.z, g.x, g.y, g.z, q.w, q.x, q.y, q.z);
}
