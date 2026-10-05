import { spawnSync } from 'node:child_process';

const BRIDGE = __CREWLOOM_BRIDGE_ARGV__;
const ROOT = __CREWLOOM_ROOT__;
const PROJECT_ID = __CREWLOOM_PROJECT_ID__;
const HOST = 'opencode';
const CONFIG_SHA = __CREWLOOM_CONFIG_SHA__;
const BRIDGE_TIMEOUT_MS = 150000;
/* The engine refuses a turn_id that is not explicit nonempty text, so the adapter refuses an
   implausible identity here with a real reason instead of spending a bridge round trip on it. */
const MAX_ID_LENGTH = 200;

function call(stage, payload) {
  const argv = BRIDGE.concat([
    'event', '--project', ROOT, '--project-id', PROJECT_ID, '--host', HOST,
    '--stage', stage, '--config-sha', CONFIG_SHA,
  ]);
  const result = spawnSync(argv[0], argv.slice(1), {
    input: JSON.stringify(payload),
    encoding: 'utf8',
    timeout: BRIDGE_TIMEOUT_MS,
    cwd: ROOT,
    maxBuffer: 8 * 1024 * 1024,
  });
  if (result.error) return { error: 'Crewloom lifecycle bridge failed: ' + String(result.error.message).slice(0, 300) };
  if (result.status !== 0) {
    const detail = String(result.stderr || '').trim().slice(0, 300);
    return { error: 'Crewloom lifecycle bridge refused this step: ' + (detail || 'exit ' + result.status) };
  }
  try {
    return JSON.parse(result.stdout || '{}');
  } catch (error) {
    return { error: 'Crewloom lifecycle bridge returned malformed JSON' };
  }
}

function refuse(reason) {
  throw new Error(String(reason).slice(0, 800));
}

/* One declared identity, or nothing. A host that sent a value is never treated as a host that
   sent nothing, so a malformed identity is refused rather than quietly dropped. */
function declaredID(value, label) {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string' || !value.trim() || value.length > MAX_ID_LENGTH) {
    refuse('Crewloom received a host ' + label + ' that is not a real turn identity.');
  }
  return value;
}

/* The real turn identity of one callback. OpenCode 1.18.32 generates the user turn itself and
   delivers it as `output.message`, while `input.messageID` is optional in the installed hook
   types, so a callback carrying only the generated message is a normal host event rather than a
   broken host: the turn is bound to whichever real identity arrived. A generated message also
   has to belong to this session, and two different identities for one turn are a contradiction
   that stops generation instead of choosing one of them. Nothing here invents an ID. */
function turnIdentity(sessionID, input, output) {
  const messageID = declaredID(input ? input.messageID : undefined, 'messageID');
  const message = output ? output.message : null;
  let generatedID = null;
  if (message !== null && message !== undefined) {
    if (typeof message !== 'object') refuse('Crewloom received a host turn that is not a real message.');
    generatedID = declaredID(message.id, 'generated message id');
    if (message.sessionID !== sessionID) {
      refuse('Crewloom cannot scope this turn with a host message from another session.');
    }
  }
  if (messageID && generatedID && messageID !== generatedID) {
    refuse('Crewloom cannot scope this turn with two different host message identities.');
  }
  const turnID = messageID || generatedID;
  if (!turnID) refuse('Crewloom cannot scope this turn without a real host message identity.');
  return turnID;
}

export const CrewloomLifecycle = async ({ directory, worktree }) => {
  const sessions = new Map();
  const turns = new Map();

  return {
    'chat.message': async (input, output) => {
      const sessionID = input && input.sessionID;
      if (!sessionID) refuse('Crewloom cannot scope this turn without a real host sessionID.');
      const turnID = turnIdentity(sessionID, input, output);
      sessions.set(sessionID, directory);
      turns.set(sessionID, turnID);
      const response = call('prepare', {
        session_id: sessionID,
        turn_id: turnID,
        cwd: directory,
        worktree: worktree || null,
        host_version: null,
        agent: input.agent || null,
        model: input.model || null,
        variant: input.variant === undefined ? null : input.variant,
      });
      if (response && response.error) refuse(response.error);
    },

    'experimental.chat.system.transform': async (input, output) => {
      const sessionID = (input && input.sessionID) || null;
      if (!sessionID) refuse('Crewloom cannot inject context without a real host sessionID.');
      const turnID = turns.get(sessionID);
      if (!turnID) refuse('Crewloom has no prepared turn for session ' + String(sessionID) + '.');
      const response = call('inject', {
        session_id: sessionID,
        turn_id: turnID,
        cwd: sessions.get(sessionID) || directory,
        model: (input && input.model) || null,
      });
      if (response && response.error) refuse(response.error);
      if (!response || !response.additionalContext) {
        refuse('Crewloom produced no context for this turn; generation stops rather than continue '
               + 'without the project contract.');
      }
      if (!output || !Array.isArray(output.system)) {
        refuse('Crewloom cannot inject context because the host did not supply a system prompt array to extend.');
      }
      // The host owns this array: replacing it leaves the model without the context.
      output.system.push(response.additionalContext);
    },

    'tool.execute.before': async (input, output) => {
      const sessionID = (input && input.sessionID) || null;
      const args = (output && output.args) || {};
      const response = call('guard', {
        session_id: sessionID,
        turn_id: sessionID ? turns.get(sessionID) || null : null,
        cwd: sessions.get(sessionID) || directory,
        call_id: (input && input.callID) || null,
        tool: (input && input.tool) || null,
        args,
      });
      if (response && response.error) refuse(response.error);
      if (response && response.permissionDecision === 'deny') refuse(response.permissionDecisionReason);
    },

    'tool.execute.after': async (input) => {
      const sessionID = (input && input.sessionID) || null;
      const response = call('checkpoint', {
        session_id: sessionID,
        turn_id: sessionID ? turns.get(sessionID) || null : null,
        cwd: sessions.get(sessionID) || directory,
        call_id: (input && input.callID) || null,
        tool: (input && input.tool) || null,
        args: (input && input.args) || {},
      });
      if (response && response.error) refuse(response.error);
    },

    event: async (input) => {
      const event = (input && input.event) || {};
      const properties = event.properties || {};
      const sessionID = properties.sessionID || null;
      if (!sessionID) return;
      if (!sessions.has(sessionID)) return;
      const payload = {
        session_id: sessionID,
        turn_id: turns.get(sessionID) || null,
        cwd: sessions.get(sessionID) || directory,
      };
      if (event.type === 'session.idle') {
        call('verify', Object.assign({ reason: 'session.idle' }, payload));
      } else if (event.type === 'session.error') {
        call('close', Object.assign({ reason: 'session.error' }, payload));
      }
    },
  };
};