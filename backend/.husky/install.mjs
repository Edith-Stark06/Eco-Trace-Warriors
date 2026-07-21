// Husky's recommended production/CI setup — skips Git hook installation
// when devDependencies are omitted (Docker runtime image) or on CI servers.
// https://typicode.github.io/husky/how-to.html#ci-server-and-docker
if (
  process.env.HUSKY === '0' ||
  process.env.NODE_ENV === 'production' ||
  process.env.CI === 'true'
) {
  process.exit(0);
}

// .git lives at the repository root, one level above backend/
process.chdir('..');
const husky = (await import('husky')).default;
console.log(husky('backend/.husky'));
