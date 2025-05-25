/*
   2× LED + LDR – plynulá PI regulácia (20 Hz) s anti-wind-up
   ----------------------------------------------------------
   Protokol:
       MCU → PC : "L,<ldr>,PWM1,<p1>,PWM2,<p2>\n"  (50 ms)
       PC  → MCU: "S,<ref>\n"                      (0-1023)
*/

// -------------------- HW piny -------------------------------
const uint8_t LED1_PIN = 9;          // Timer1 PWM ~490 Hz
const uint8_t LED2_PIN = 10;
const uint8_t LDR_PIN  = A0;

// -------------------- parametre -----------------------------
const unsigned long LOOP_DT = 50;    // [ms] regulačná slučka = 20 Hz
const uint8_t  AVG_LEN  = 4;         // moving-average dĺžka (≈200 ms okno)

const float KP = 0.9;                // P zložka
const float KI = 0.5;               // I zložka (1/s)

const int8_t PWM_SLEW = 10;           // max. zmena PWM za cyklus (±5)

// -------------------- premenné ------------------------------
uint16_t setPoint = 800;

uint16_t ring[AVG_LEN];
uint8_t  ringPos = 0;

float    integ   = 0;                // I-člen
uint16_t lastOut = 0;                // predchádzajúci súčet PWM
unsigned long prevT = 0;

String serialBuffer;

// ============================================================
//  Pomocná funkcia – príjem príkazu S,<ref>
// ============================================================
void processCommand(const String& cmd)
{
  if (cmd.startsWith("S,")) {
    int val = cmd.substring(2).toInt();
    setPoint = constrain(val, 0, 1023);
  }
}

// ============================================================
void setup()
{
  Serial.begin(115200);
  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);

  uint16_t first = analogRead(LDR_PIN);   // vyplň kruhový buffer
  for (uint8_t i = 0; i < AVG_LEN; ++i) ring[i] = first;
}

// ============================================================
void loop()
{
  /* --- UART príkazy --------------------------------------- */
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n')      { processCommand(serialBuffer); serialBuffer=""; }
    else if (c != '\r')   serialBuffer += c;
  }

  /* --- cyklus: 50 ms -------------------------------------- */
  unsigned long now = millis();
  if (now - prevT < LOOP_DT) return;
  prevT = now;

  /* --- meranie + moving-average --------------------------- */
  uint16_t raw = analogRead(LDR_PIN);
  ring[ringPos] = raw;
  ringPos = (ringPos + 1) % AVG_LEN;

  uint32_t sum = 0;
  for (uint8_t i = 0; i < AVG_LEN; ++i) sum += ring[i];
  uint16_t ldr = sum / AVG_LEN;          // odfiltrovaná hodnota

  /* --- PI regulátor s anti-wind-up ------------------------ */
  float error = (float)ldr - setPoint;   // tma ⇒ kladná chyba

  /* 1) P-zložka */
  float pTerm = (error > 0) ? KP * error : 0.0f;

  /* 2) I-zložka – integraj iba ak výstup nebude saturovaný */
  if (error > 0 && lastOut < 510) {
    integ += error * KI * (LOOP_DT / 1000.0f);
    if (integ > 510) integ = 510;        // horná medza integrátora
  } else {
    /* jemné “únikanie” integrálu, aby po zhasnutí LED pomaly klesal */
    integ *= 0.97f;                      // 3 % úbytok za cyklus
  }

  float outF = pTerm + integ;
  if (outF > 510) outF = 510;            // saturácia
  uint16_t out = (uint16_t)outF;

  /* --- slew-rate (symetrický) ----------------------------- */
  if      (out > lastOut + PWM_SLEW) out = lastOut + PWM_SLEW;
  else if (out + PWM_SLEW < lastOut) out = lastOut - PWM_SLEW;
  lastOut = out;

  /* --- rozdelenie na dve LED ------------------------------ */
  uint8_t pwm1 = (out >= 255) ? 255 : out;
  uint8_t pwm2 = (out >= 255) ? (out - 255) : 0;

  analogWrite(LED1_PIN, pwm1);
  analogWrite(LED2_PIN, pwm2);

  /* --- telemetria ----------------------------------------- */
  Serial.print(F("L,"));    Serial.print(ldr);
  Serial.print(F(",PWM1,")); Serial.print(pwm1);
  Serial.print(F(",PWM2,")); Serial.println(pwm2);
}
