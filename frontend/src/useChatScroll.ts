import { useLayoutEffect, useRef, useState } from 'react';
import { ChatScrollController, observeChatHistory } from './chatScroll';
import type { LobbyState } from './types';

export function useChatScroll(messages: LobbyState['chat'], you: string) {
  const history = useRef<HTMLDivElement>(null);
  const contents = useRef<HTMLOListElement>(null);
  const controller = useRef<ChatScrollController | null>(null);
  const [unread, setUnread] = useState(0);
  useLayoutEffect(() => {
    if (!history.current || !contents.current) return;
    const view = new ChatScrollController(history.current, you, setUnread);
    controller.current = view;
    setUnread(0);
    const stop = observeChatHistory(history.current, contents.current, view);
    return () => { stop(); controller.current = null; };
  }, [you]);
  useLayoutEffect(() => { controller.current?.update(messages); }, [messages, you]);
  return { history, contents, unread, jumpToLatest: () => controller.current?.jumpToLatest() };
}
