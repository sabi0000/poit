#include <Servo.h>

const int trigPin = 9;
const int echoPin = 10;
const int servoPin = 11;
const int flameSensorPin = A0;
const int buzzerPin = 12;

float duration, distance;
Servo rampServo;

void setup() {
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(flameSensorPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  Serial.begin(115200);
  rampServo.attach(servoPin);
  rampServo.write(0);
}

void loop() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  duration = pulseIn(echoPin, HIGH);
  distance = (duration * 0.0343) / 2;

  int flameValue = analogRead(flameSensorPin);

  String jsonData = "{\"distance\": " + String(distance) + ", \"flameValue\": " + String(flameValue) + "}";
  Serial.println(jsonData);


  // Ovládanie serva podľa vzdialenosti alebo hodnoty z flame senzora
  if (distance < 10 || flameValue < 100) {
    rampServo.write(90); // Otvorenie rampy (o 90 stupňov)
  } else {
    rampServo.write(0); // Zatvorenie rampy
  }

  // Spustenie sirény pri nízkej hodnote z flame senzora
  if (flameValue < 100) {
    digitalWrite(buzzerPin, HIGH); // Zapnutie sirény
  } else {
    digitalWrite(buzzerPin, LOW); // Vypnutie sirény
  }
  delay(500);
}
