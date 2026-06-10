import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

const sourceIndex = new URL('../index.src.html', import.meta.url);
const pagesIndex = new URL('../index.html', import.meta.url);
const distData = new URL('../dist/dashboard-data.js', import.meta.url);
const distCandidateSummary = new URL('../dist/candidates-summary.json', import.meta.url);
const distNotifications = new URL('../dist/dashboard-notifications.js', import.meta.url);

const originalIndex = await readFile(pagesIndex, 'utf8');

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit' });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} ${args.join(' ')} failed with exit code ${code}`));
    });
  });
}

try {
  const devIndex = await readFile(sourceIndex, 'utf8');
  await writeFile(pagesIndex, devIndex);
  await run('vite', ['build']);
  await mkdir(new URL('../dist', import.meta.url), { recursive: true });
  await copyFile(new URL('../dashboard-data.js', import.meta.url), distData);
  await copyFile(new URL('../candidates-summary.json', import.meta.url), distCandidateSummary);
  await copyFile(new URL('../dashboard-notifications.js', import.meta.url), distNotifications);
} finally {
  await writeFile(pagesIndex, originalIndex);
}
