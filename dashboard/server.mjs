import { createServer } from 'node:http';
import next from 'next';

// One launch path owns both the real socket and the password-free access decision.
const args = process.argv.slice(2);
let hostname = process.env.CREWLOOM_DASHBOARD_HOST || '127.0.0.1';
let port = Number(process.env.CREWLOOM_DASHBOARD_PORT || 4317);
const dev = args.includes('--dev');
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dev') continue;
  if (['-H', '--hostname'].includes(args[i])) hostname = args[++i];
  else if (['-p', '--port'].includes(args[i])) port = Number(args[++i]);
  else throw new Error(`Unknown dashboard argument: ${args[i]}`);
}
if (!hostname || !Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('A hostname and port between 1 and 65535 are required');
}
process.env.CREWLOOM_DASHBOARD_HOST = hostname;
process.env.CREWLOOM_DASHBOARD_PORT = String(port);
const app = next({ dev, hostname, port });
await app.prepare();
const handle = app.getRequestHandler();
const server = createServer((req, res) => handle(req, res));
server.on('upgrade', (req, socket, head) => app.getUpgradeHandler()(req, socket, head));
await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(port, hostname, resolve);
});
globalThis.__crewloomDashboardListener = server;
console.log(`Dashboard listening on ${hostname}:${port}`);
