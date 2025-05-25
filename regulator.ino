#include <Arduino.h>

// Hardware pins
const uint8_t LED1_PIN = 9;
const uint8_t LED2_PIN = 10;
const uint8_t LDR_PIN  = A0;

// Parameters
const unsigned long LOOP_DT = 50;    // Control loop period [ms]
const uint8_t  AVG_LEN  = 4;         // Moving average window
const float KP = 0.9;                // P gain
const float KI = 0.5;                // I gain
const int8_t PWM_SLEW = 10;          // Max PWM change per cycle

// State variables
uint16_t setPoint = 800;
uint16_t ring[AVG_LEN];
uint8_t  ringPos = 0;
float    integ   = 0;
uint16_t lastOut = 0;
unsigned long prevT = 0;
String serialBuffer;

// Handle S,<ref> command
void processCommand(const String& cmd)
{
  if (cmd.startsWith("S,")) {
    int val = cmd.substring(2).toInt();
    setPoint = constrain(val, 0, 1023);
  }
}

void setup()
{
  Serial.begin(115200);
  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);

  uint16_t first = analogRead(LDR_PIN);
  for (uint8_t i = 0; i < AVG_LEN; ++i) ring[i] = first;
}

void loop()
{
  // UART command handling
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n')      { processCommand(serialBuffer); serialBuffer=""; }
    else if (c != '\r')   serialBuffer += c;
  }

  // 50 ms control loop
  unsigned long now = millis();
  if (now - prevT < LOOP_DT) return;
  prevT = now;

  // LDR measurement and moving average
  uint16_t raw = analogRead(LDR_PIN);
  ring[ringPos] = raw;
  ringPos = (ringPos + 1) % AVG_LEN;
  uint32_t sum = 0;
  for (uint8_t i = 0; i < AVG_LEN; ++i) sum += ring[i];
  uint16_t ldr = sum / AVG_LEN;

  // PI controller with anti-windup
  float error = (float)ldr - setPoint;
  float pTerm = (error > 0) ? KP * error : 0.0f;
  if (error > 0 && lastOut < 510) {
    integ += error * KI * (LOOP_DT / 1000.0f);
    if (integ > 510) integ = 510;
  } else {
    integ *= 0.97f;
  }
  float outF = pTerm + integ;
  if (outF > 510) outF = 510;
  uint16_t out = (uint16_t)outF;

  // Slew rate limiting
  if      (out > lastOut + PWM_SLEW) out = lastOut + PWM_SLEW;
  else if (out + PWM_SLEW < lastOut) out = lastOut - PWM_SLEW;
  lastOut = out;

  // Split output to two LEDs
  uint8_t pwm1 = (out >= 255) ? 255 : out;
  uint8_t pwm2 = (out >= 255) ? (out - 255) : 0;

  analogWrite(LED1_PIN, pwm1);
  analogWrite(LED2_PIN, pwm2);

  // Telemetry output
  Serial.print(F("L,"));    Serial.print(ldr);
  Serial.print(F(",PWM1,")); Serial.print(pwm1);
  Serial.print(F(",PWM2,")); Serial.println(pwm2);
}
