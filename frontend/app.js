/**
 * Lumen Frontend — SSE Chat Client
 *
 * Connects to POST /api/chat and streams token-by-token responses.
 * Renders citations panel after generation completes.
 */

const API_BASE = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------

const State = {
    currentPersona: 'kardec',
    sessionId: null,
    history: [],          // [{role, content}, ...]
    isStreaming: false,
    currentAssistantEl: null,
    currentTextBuffer: '',
};

// ---------------------------------------------------------------------------
// DOM refs (populated after DOMContentLoaded)
// ---------------------------------------------------------------------------

let $input, $sendBtn, $messagesArea, $welcomeScreen, $personaSelect;

document.addEventListener('DOMContentLoaded', () => {
    $input        = document.getElementById('message-input');
    $sendBtn      = document.getElementById('send-btn');
    $messagesArea = document.getElementById('messages-area');
    $welcomeScreen = document.getElementById('welcome-screen');
    $personaSelect = document.getElementById('agent-select');

    loadTheme();
    checkHealth();
    $input.focus();

    $personaSelect.addEventListener('change', (e) => {
        State.currentPersona = e.target.value;
        if (State.history.length > 0) {
            _appendSystemNote(`Agora conversando com ${_personaName(State.currentPersona)}`);
        }
    });
});

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        const dot = document.getElementById('health-dot');
        const label = document.getElementById('health-label');
        if (!dot || !label) return;
        if (data.status === 'ok') {
            dot.className = 'w-2 h-2 rounded-full bg-green-500';
            label.textContent = 'Sistema online';
        } else if (data.status === 'degraded') {
            dot.className = 'w-2 h-2 rounded-full bg-yellow-400';
            label.textContent = 'Modo degradado';
        } else {
            dot.className = 'w-2 h-2 rounded-full bg-red-500';
            label.textContent = 'Sistema offline';
        }
    } catch {
        const dot = document.getElementById('health-dot');
        const label = document.getElementById('health-label');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-red-500';
        if (label) label.textContent = 'Backend inacessível';
    }
}

// ---------------------------------------------------------------------------
// Send message
// ---------------------------------------------------------------------------

async function sendMessage() {
    if (!$input) return;
    const text = $input.value.trim();
    if (!text || State.isStreaming) return;

    // Show chat area, hide welcome
    $welcomeScreen.classList.add('hidden');
    $messagesArea.classList.remove('hidden');

    // Append user bubble
    _appendUserBubble(text);
    $input.value = '';
    $input.style.height = 'auto';

    // Add to history
    State.history.push({ role: 'user', content: text });

    // Show typing indicator
    const typingEl = _showTyping();
    State.isStreaming = true;
    $sendBtn.disabled = true;

    // Create assistant bubble (hidden until first token)
    const { wrapper, textEl, citationsEl } = _createAssistantBubble();
    $messagesArea.appendChild(wrapper);
    State.currentAssistantEl = textEl;
    State.currentTextBuffer = '';

    // Start SSE stream
    try {
        await _streamChat(text, textEl, citationsEl);
    } catch (err) {
        _appendErrorNote(`Erro: ${err.message}`);
    } finally {
        typingEl.remove();
        wrapper.style.opacity = '1';
        State.isStreaming = false;
        $sendBtn.disabled = false;
        State.currentAssistantEl = null;
    }
}

// ---------------------------------------------------------------------------
// SSE streaming
// ---------------------------------------------------------------------------

async function _streamChat(userMessage, textEl, citationsEl) {
    const body = {
        message: userMessage,
        persona_id: State.currentPersona,
        session_id: State.sessionId,
        history: State.history.slice(0, -1), // exclude the just-added user turn
        options: {
            max_new_tokens: 1024,
            top_k_chunks: 10,
            temperature: 0.7,
        },
    };

    const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let eventType = null;
    let fullText = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // keep incomplete last line

        for (const line of lines) {
            if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
                const raw = line.slice(6).trim();

                if (raw === '[DONE]') {
                    // Stream finished — push final assistant turn to history
                    State.history.push({ role: 'assistant', content: fullText });
                    return;
                }

                let data;
                try {
                    data = JSON.parse(raw);
                } catch {
                    continue;
                }

                if (eventType === 'token') {
                    fullText += data.token;
                    textEl.textContent += data.token;
                    _scrollToBottom();

                } else if (eventType === 'citations') {
                    _renderCitations(citationsEl, data.citations || []);

                } else if (eventType === 'stats') {
                    if (data.stats?.session_id) {
                        State.sessionId = data.stats.session_id;
                    }
                    _renderStats(citationsEl, data.stats);

                } else if (eventType === 'error') {
                    throw new Error(data.detail || 'Unknown error');
                }

                eventType = null;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// DOM builders
// ---------------------------------------------------------------------------

function _appendUserBubble(text) {
    const div = document.createElement('div');
    div.className = 'message-enter flex gap-4 flex-row-reverse';
    div.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-gray-300 dark:bg-gray-600 flex-shrink-0 flex items-center justify-center text-xs font-medium">Eu</div>
        <div class="flex-1 text-right">
            <div class="inline-block max-w-[85%] bg-gray-100 dark:bg-gray-800 rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm border border-gray-200 dark:border-gray-700 text-left">
                ${_escapeHtml(text)}
            </div>
        </div>`;
    $messagesArea.appendChild(div);
    _scrollToBottom();
}

function _createAssistantBubble() {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-enter flex gap-4';
    wrapper.style.opacity = '0';
    wrapper.style.transition = 'opacity 0.2s';

    const textEl = document.createElement('div');
    textEl.className = 'text-sm leading-relaxed whitespace-pre-wrap';

    const citationsEl = document.createElement('div');
    citationsEl.className = 'mt-3 pt-2 border-t border-gray-100 dark:border-gray-700 space-y-1 hidden';

    wrapper.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex-shrink-0 flex items-center justify-center">
            <svg class="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C10 6 8 8 8 11C8 13 9 15 10 16C9 16 8 15 7 14C6 18 8 21 12 22C16 21 18 18 17 14C16 15 15 16 14 16C15 15 16 13 16 11C16 8 14 6 12 2Z"/>
            </svg>
        </div>
        <div class="flex-1 min-w-0">
            <div class="inline-block max-w-full bg-white dark:bg-gray-900 rounded-2xl px-4 py-2.5 shadow-sm border border-gray-100 dark:border-gray-800">
            </div>
        </div>`;

    const bubble = wrapper.querySelector('.rounded-2xl');
    bubble.appendChild(textEl);
    bubble.appendChild(citationsEl);

    // Make bubble visible as soon as first token arrives
    const observer = new MutationObserver(() => {
        if (textEl.textContent.length > 0) {
            wrapper.style.opacity = '1';
            observer.disconnect();
        }
    });
    observer.observe(textEl, { characterData: true, childList: true });

    return { wrapper, textEl, citationsEl };
}

function _renderCitations(container, citations) {
    if (!citations || citations.length === 0) return;
    container.classList.remove('hidden');
    container.innerHTML = '<p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Fontes</p>';

    citations.forEach(c => {
        const btn = document.createElement('button');
        btn.className =
            'inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full ' +
            'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 ' +
            'border border-orange-200 dark:border-orange-700 hover:bg-orange-100 ' +
            'dark:hover:bg-orange-900/40 transition mr-1 mb-1';
        btn.title = c.excerpt || '';
        btn.textContent = c.label;
        btn.onclick = () => _showCitationModal(c);
        container.appendChild(btn);
    });
}

function _renderStats(container, stats) {
    if (!stats) return;
    const el = document.createElement('p');
    el.className = 'text-[10px] text-gray-400 dark:text-gray-500 mt-1';
    el.textContent = `${stats.tokens_generated} tokens · ${stats.tokens_per_second} tok/s · RAG ${stats.rag_latency_ms}ms`;
    container.appendChild(el);
    container.classList.remove('hidden');
}

function _showCitationModal(c) {
    // Simple modal using alert for Phase 1; can be upgraded later
    const text = [
        `📖 ${c.obra}`,
        c.parte ? `Parte: ${c.parte}` : null,
        c.capitulo ? `Capítulo: ${c.capitulo}` : null,
        c.questao ? `Questão: ${c.questao}` : null,
        '',
        c.excerpt,
    ].filter(l => l !== null).join('\n');
    alert(text);
}

function _showTyping() {
    const div = document.createElement('div');
    div.id = 'typing-indicator';
    div.className = 'message-enter flex gap-4';
    div.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex-shrink-0 flex items-center justify-center">
            <svg class="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C10 6 8 8 8 11C8 13 9 15 10 16C9 16 8 15 7 14C6 18 8 21 12 22C16 21 18 18 17 14C16 15 15 16 14 16C15 15 16 13 16 11C16 8 14 6 12 2Z"/>
            </svg>
        </div>
        <div class="flex items-center gap-1 px-4 py-4 bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm">
            <div class="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full typing-dot"></div>
        </div>`;
    $messagesArea.appendChild(div);
    _scrollToBottom();
    return div;
}

function _appendSystemNote(text) {
    const div = document.createElement('div');
    div.className = 'flex justify-center my-2';
    div.innerHTML = `<span class="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">${_escapeHtml(text)}</span>`;
    $messagesArea.appendChild(div);
    _scrollToBottom();
}

function _appendErrorNote(text) {
    const div = document.createElement('div');
    div.className = 'flex justify-center my-2';
    div.innerHTML = `<span class="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 px-3 py-1 rounded-full">${_escapeHtml(text)}</span>`;
    $messagesArea.appendChild(div);
    _scrollToBottom();
}

// ---------------------------------------------------------------------------
// Utility functions (called from inline handlers in index.html)
// ---------------------------------------------------------------------------

function newChat() {
    $welcomeScreen.classList.remove('hidden');
    $messagesArea.classList.add('hidden');
    $messagesArea.innerHTML = '';
    State.history = [];
    State.sessionId = null;
    if (window.innerWidth < 768) toggleSidebar();
}

function startQuickChat(persona) {
    $personaSelect.value = persona;
    State.currentPersona = persona;
    newChat();
    $input.focus();
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 128) + 'px';
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const isOpen = !sidebar.classList.contains('-translate-x-full');
    if (isOpen) {
        sidebar.classList.add('-translate-x-full');
        overlay.classList.add('hidden');
    } else {
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.remove('hidden');
    }
}

function toggleTheme() {
    const html = document.documentElement;
    if (html.classList.contains('dark')) {
        html.classList.remove('dark');
        localStorage.setItem('theme', 'light');
    } else {
        html.classList.add('dark');
        localStorage.setItem('theme', 'dark');
    }
}

function loadTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _scrollToBottom() {
    const container = document.getElementById('chat-container');
    if (container) container.scrollTop = container.scrollHeight;
}

function _escapeHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _personaName(id) {
    const names = {
        kardec: 'Allan Kardec',
        andreluiz: 'André Luiz',
        emmanuel: 'Emmanuel',
        joana: 'Joana de Angelis',
    };
    return names[id] || id;
}
