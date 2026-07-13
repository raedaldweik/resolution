import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getSessions, getSessionQueries } from '../services/api';

const ChatContext = createContext();

const WELCOME = {
  role: 'assistant',
  type: 'text',
  content: "Welcome to the MoCE Agent Ecosystem. Pick an agent from the dropdown above — Document Processing (OCR + extraction), Knowledge & Policy (grounded policy answers with citations), or Customer Resolution (investigates benefit issues end-to-end) — and ask anything.",
};
const id = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

const NEW_TITLE = 'New conversation';

// Rebuild chat bubbles from RAM's persisted query records
function messagesFromQueries(queries) {
  const msgs = [WELCOME];
  for (const q of queries) {
    // Only top-level user turns are chat bubbles. Agent runs spawn internal
    // sub-queries (origin "agent" / a parentQueryId) under the same session —
    // those are agent-to-agent calls, not messages, so never render them.
    if (q.parentQueryId || (q.origin && q.origin !== 'user')) continue;
    msgs.push({ role: 'user', type: 'text', content: q.content });
    if (q.errorCode && q.errorCode !== 0) {
      msgs.push({ role: 'assistant', type: 'text', content: `Error: ${q.errorText || 'query failed'}`, isError: true });
    } else if (q.answer != null) {
      msgs.push({ role: 'assistant', type: 'structured', data: q, query: q.content });
    }
  }
  return msgs;
}

export function ChatProvider({ children }) {
  const [chats, setChats] = useState([{ id: id(), sessionId: null, title: NEW_TITLE, messages: [WELCOME], loaded: true }]);
  const [activeChatId, setActiveChatId] = useState(chats[0].id);

  const activeChat = chats.find(c => c.id === activeChatId) || chats[0];

  // Pull past query sessions from RAM so history survives reloads
  useEffect(() => {
    getSessions().then(sessions => {
      setChats(prev => {
        const known = new Set(prev.map(c => c.sessionId).filter(Boolean));
        const stubs = sessions
          .filter(s => s.id && !known.has(s.id))
          .map(s => ({
            id: id(), sessionId: s.id, title: s.title || 'Conversation', messages: [WELCOME], loaded: false,
            // which agent/collections this session talked to (for sidebar scoping)
            agentId: s.agentId || null, collectionIds: s.collectionIds || [],
          }));
        return [...prev, ...stubs];
      });
    }).catch(() => {});
  }, []);

  // Lazy-load a server session's messages the first time it's opened
  useEffect(() => {
    const chat = chats.find(c => c.id === activeChatId);
    if (!chat || chat.loaded || !chat.sessionId) return;
    getSessionQueries(chat.sessionId)
      .then(queries => {
        setChats(prev => prev.map(c => c.id === chat.id ? { ...c, loaded: true, messages: messagesFromQueries(queries) } : c));
      })
      .catch(() => {
        setChats(prev => prev.map(c => c.id === chat.id ? { ...c, loaded: true } : c));
      });
  }, [activeChatId, chats]);

  const createNewChat = useCallback(() => {
    const c = { id: id(), sessionId: null, title: NEW_TITLE, messages: [WELCOME], loaded: true };
    setChats(p => [c, ...p]);
    setActiveChatId(c.id);
  }, []);

  const addMessage = useCallback((chatId, msg) => {
    setChats(p => p.map(c => {
      if (c.id !== chatId) return c;
      const updated = { ...c, messages: [...c.messages, msg] };
      if (msg.role === 'user' && c.title === NEW_TITLE)
        updated.title = msg.content.slice(0, 40) + (msg.content.length > 40 ? '...' : '');
      return updated;
    }));
  }, []);

  // Record the querySessionId RAM assigned on the first reply, plus the
  // target it was created against so the sidebar can scope by agent/collection
  const setChatSession = useCallback((chatId, sessionId, target = null) => {
    setChats(p => p.map(c => {
      if (c.id !== chatId || c.sessionId) return c;
      return {
        ...c, sessionId,
        agentId: target?.type === 'agent' ? target.id : c.agentId || null,
        collectionIds: target?.type === 'collection' ? [target.id] : c.collectionIds || [],
      };
    }));
  }, []);

  const renameChat = useCallback((chatId, newTitle) => {
    setChats(p => p.map(c => c.id === chatId ? { ...c, title: newTitle } : c));
  }, []);

  const deleteChat = useCallback((chatId) => {
    setChats(p => {
      const filtered = p.filter(c => c.id !== chatId);
      const next = filtered.length === 0
        ? [{ id: id(), sessionId: null, title: NEW_TITLE, messages: [WELCOME], loaded: true }]
        : filtered;
      // Keep the active chat valid against the *new* list (derived here, not
      // from a possibly-stale closure): if the deleted chat was active, or the
      // list was reset to a fresh chat, switch to the first remaining chat.
      setActiveChatId(curr => (next.some(c => c.id === curr) ? curr : next[0].id));
      return next;
    });
  }, []);

  return (
    <ChatContext.Provider value={{ chats, activeChat, activeChatId, setActiveChatId, createNewChat, addMessage, setChatSession, renameChat, deleteChat }}>
      {children}
    </ChatContext.Provider>
  );
}

export const useChat = () => useContext(ChatContext);
