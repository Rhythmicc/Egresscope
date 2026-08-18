const PASSWORD_SETS = [
  "ABCDEFGHJKLMNPQRSTUVWXYZ",
  "abcdefghijkmnopqrstuvwxyz",
  "23456789",
  "!@#$%&*+-=?_",
];

const randomIndex = (maximum) => {
  const ceiling = Math.floor(256 / maximum) * maximum;
  const value = new Uint8Array(1);
  do crypto.getRandomValues(value); while (value[0] >= ceiling);
  return value[0] % maximum;
};

const takeRandom = characters => characters[randomIndex(characters.length)];

export function generateRandomPassword(length = 20) {
  const targetLength = Math.max(12, length);
  const all = PASSWORD_SETS.join("");
  const password = PASSWORD_SETS.map(takeRandom);
  while (password.length < targetLength) password.push(takeRandom(all));
  for (let index = password.length - 1; index > 0; index -= 1) {
    const swap = randomIndex(index + 1);
    [password[index], password[swap]] = [password[swap], password[index]];
  }
  return password.join("");
}
