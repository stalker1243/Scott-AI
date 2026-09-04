// Короткие фразы-подтверждения в духе "живого" ИИ-ассистента — произносятся
// сразу после отправки сообщения, ещё до готовности реального ответа.

const ACKNOWLEDGEMENTS = [
  "Есть, сэр!",
  "Уже выполняю, сэр.",
  "Принято, секунду.",
  "Сию минуту.",
  "Работаю над этим.",
  "Хорошо, сэр, приступаю.",
  "Понял вас.",
];

let lastIndex = -1;

export function pickAcknowledgement(): string {
  let index = Math.floor(Math.random() * ACKNOWLEDGEMENTS.length);
  if (index === lastIndex) {
    index = (index + 1) % ACKNOWLEDGEMENTS.length;
  }
  lastIndex = index;
  return ACKNOWLEDGEMENTS[index];
}
