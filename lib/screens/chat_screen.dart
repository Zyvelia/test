// chat_screen.dart — streaming chat with memory sidebar, appearance menu,
//                    in-chat persona switcher, and chat history drawer

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/app_provider.dart';
import '../services/storage_service.dart';
import '../services/ollama_service.dart';
import '../theme.dart';

// ── Appearance palette ────────────────────────────────────────────────────────

const _bubblePalette = [
  [Color(0xFF7C6CF0), Color(0xFFD45FA6)],  // 0 violet-pink  (default user)
  [Color(0xFF1B1B29), Color(0xFF1B1B29)],  // 1 dark         (default char)
  [Color(0xFF0D3B6E), Color(0xFF1565C0)],  // 2 deep blue
  [Color(0xFF1B3A1B), Color(0xFF2E7D32)],  // 3 forest green
  [Color(0xFF3B1F1F), Color(0xFF7B1A1A)],  // 4 deep red
  [Color(0xFF2A1C3C), Color(0xFF6A1B9A)],  // 5 deep purple
  [Color(0xFF1A2A2A), Color(0xFF00838F)],  // 6 teal
  [Color(0xFF3B2A00), Color(0xFFF57C00)], // 7 amber
];

const _bgPresets = <BackgroundPreset, List<Color>>{
  BackgroundPreset.default_: [Color(0xFF0B0B12), Color(0xFF0B0B12)],
  BackgroundPreset.midnight: [Color(0xFF070714), Color(0xFF10103A)],
  BackgroundPreset.dusk:     [Color(0xFF1A0A14), Color(0xFF2A0A2A)],
  BackgroundPreset.forest:   [Color(0xFF070F07), Color(0xFF0F1A0F)],
  BackgroundPreset.ocean:    [Color(0xFF060E14), Color(0xFF081A24)],
  BackgroundPreset.rose:     [Color(0xFF160810), Color(0xFF260818)],
};

const _bgLabels = <BackgroundPreset, String>{
  BackgroundPreset.default_: 'Default',
  BackgroundPreset.midnight: 'Midnight',
  BackgroundPreset.dusk:     'Dusk',
  BackgroundPreset.forest:   'Forest',
  BackgroundPreset.ocean:    'Ocean',
  BackgroundPreset.rose:     'Rose',
};

const _bubbleLabels = [
  'Violet', 'Dark', 'Blue', 'Green', 'Red', 'Purple', 'Teal', 'Amber',
];

// ── ChatScreen ────────────────────────────────────────────────────────────────

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _scrollCtrl = ScrollController();
  List<ChatMessage> _history = [];
  bool _streaming = false;
  String _streamingText = '';
  String? _error;
  bool _showMemory = false;
  List<String> _memFacts = [];
  String? _loadedCharId;

  Character? get _char => context.read<AppProvider>().activeChar;

  @override
  void dispose() {
    _input.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _loadChat() {
    final c = _char;
    if (c == null) { setState(() => _history = []); return; }
    final store = StorageService.instance;
    var history = store.loadChat(c.id);
    if (history.isEmpty && c.greeting.isNotEmpty) {
      history = [ChatMessage(role: 'assistant', content: c.greeting)];
      store.saveChat(c.id, history);
    }
    _memFacts = store.loadMemory(c.id);
    setState(() { _history = history; });
    _scrollBottom();
  }

  void _scrollBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final c = _char;
    if (c == null || _input.text.trim().isEmpty || _streaming) return;
    final userMsg = _input.text.trim();
    _input.clear();
    _history.add(ChatMessage(role: 'user', content: userMsg));
    StorageService.instance.saveChat(c.id, _history);
    await _generate(extractAfter: true);
  }

  Future<void> _regenerate() async {
    final c = _char;
    if (c == null || _streaming) return;
    while (_history.isNotEmpty && _history.last.isAssistant) {
      _history.removeLast();
    }
    StorageService.instance.saveChat(c.id, _history);
    setState(() {});
    if (_history.isNotEmpty) await _generate();
  }

  Future<void> _generate({bool extractAfter = false}) async {
    final c = _char;
    if (c == null) return;
    final ap = context.read<AppProvider>();
    final s = ap.settings;
    final persona = ap.activePersona;

    setState(() { _streaming = true; _streamingText = ''; _error = null; });
    _scrollBottom();

    final systemPrompt = OllamaService.instance.buildSystemPrompt(c, s, persona, _memFacts);
    final ctx = _history.length > s.contextWindow
        ? _history.sublist(_history.length - s.contextWindow)
        : _history;
    final messages = [
      {'role': 'system', 'content': systemPrompt},
      ...ctx.map((m) => {'role': m.role, 'content': m.content}),
    ];

    try {
      await for (final chunk in OllamaService.instance.streamChat(
        baseUrl: s.ollamaUrl,
        model: s.model,
        messages: messages,
      )) {
        if (!mounted) return;
        setState(() => _streamingText += chunk);
        _scrollBottom();
      }

      final response = _streamingText.trim();
      if (response.isEmpty) {
        throw Exception('The model returned an empty reply. Try again, or pick a different model in Settings.');
      }
      _history.add(ChatMessage(role: 'assistant', content: response));
      StorageService.instance.saveChat(c.id, _history);
      if (!mounted) return;
      setState(() { _streaming = false; _streamingText = ''; });
      _scrollBottom();

      if (extractAfter && _history.length % 6 == 0) _extractMemory();
    } catch (e) {
      if (!mounted) return;
      final partial = _streamingText.trim();
      if (partial.isNotEmpty) {
        _history.add(ChatMessage(role: 'assistant', content: partial));
        StorageService.instance.saveChat(c.id, _history);
      }
      setState(() {
        _streaming = false;
        _streamingText = '';
        _error = OllamaService.friendlyError(e);
      });
      _scrollBottom();
    }
  }

  void _clearChat() {
    final c = _char;
    if (c == null) return;
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Clear chat'),
        content: Text('Clear all messages with ${c.name}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              StorageService.instance.clearChat(c.id);
              Navigator.pop(context);
              _loadChat();
            },
            child: const Text('Clear', style: TextStyle(color: kDanger)),
          ),
        ],
      ),
    );
  }

  void _extractMemory() async {
    final c = _char;
    if (c == null) return;
    final s = context.read<AppProvider>().settings;
    final facts = await OllamaService.instance.extractMemory(
      baseUrl: s.ollamaUrl,
      model: s.model,
      charName: c.name,
      recentMessages: _history,
    );
    if (!mounted) return;
    for (final f in facts) {
      StorageService.instance.addMemoryFact(c.id, f);
    }
    setState(() { _memFacts = StorageService.instance.loadMemory(c.id); });
  }

  // ── History drawer ────────────────────────────────────────────────────────────

  void _openHistory() {
    final c = _char;
    if (c == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _HistorySheet(
        char: c,
        onLoad: (session) {
          setState(() { _history = List.from(session.messages); });
          StorageService.instance.saveChat(c.id, _history);
          _scrollBottom();
        },
        onSaveCurrent: _history.isNotEmpty ? () {
          StorageService.instance.saveSession(c.id, c.name, _history);
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Chat saved to history')),
          );
        } : null,
      ),
    );
  }

  // ── Appearance sheet ──────────────────────────────────────────────────────────

  void _openAppearance() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AppearanceSheet(
        appearance: context.read<AppProvider>().appearance,
        onChanged: (a) => context.read<AppProvider>().saveAppearance(a),
      ),
    );
  }

  // ── Persona switcher ──────────────────────────────────────────────────────────

  void _openPersonaSwitcher() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _PersonaSwitcherSheet(
        personas: context.read<AppProvider>().personas,
        activeId: context.read<AppProvider>().settings.activePersonaId,
        onSelect: (id) => context.read<AppProvider>().setActivePersona(id),
        onDeactivate: () => context.read<AppProvider>().deactivatePersona(),
      ),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final id = context.read<AppProvider>().activeChar?.id;
    if (id != _loadedCharId && !_streaming) {
      _loadedCharId = id;
      _error = null;
      _loadChat();
    }
  }

  @override
  Widget build(BuildContext context) {
    final ap = context.watch<AppProvider>();
    final c = ap.activeChar;
    final persona = ap.activePersona;
    final appearance = ap.appearance;

    // background colours from preset
    final bgColors = _bgPresets[appearance.background] ?? _bgPresets[BackgroundPreset.default_]!;

    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        titleSpacing: 0,
        title: c == null
            ? const Padding(
                padding: EdgeInsets.only(left: 16),
                child: Text('Chat', style: TextStyle(color: kMuted)),
              )
            : Row(
                children: [
                  CharAvatar(name: c.name, path: c.avatar, size: 34, radius: 11),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(c.name,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 16)),
                        GestureDetector(
                          onTap: c != null ? _openPersonaSwitcher : null,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                _streaming
                                    ? 'typing…'
                                    : (persona != null ? 'as ${persona.name}' : 'tap to set persona'),
                                style: TextStyle(
                                  color: _streaming ? kGreen : (persona != null ? kPrimary : kMuted),
                                  fontSize: 11.5,
                                ),
                              ),
                              if (!_streaming) ...[
                                const SizedBox(width: 3),
                                Icon(Icons.arrow_drop_down, size: 14, color: persona != null ? kPrimary : kMuted),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
        actions: [
          IconButton(
            icon: const Icon(Icons.history_rounded),
            onPressed: c != null ? _openHistory : null,
            color: kMuted,
            tooltip: 'Chat history',
          ),
          IconButton(
            icon: const Icon(Icons.palette_outlined),
            onPressed: _openAppearance,
            color: kMuted,
            tooltip: 'Appearance',
          ),
          IconButton(
            icon: Icon(_showMemory ? Icons.psychology : Icons.psychology_outlined),
            onPressed: c == null ? null : () => setState(() => _showMemory = !_showMemory),
            color: _showMemory ? kPrimary : kMuted,
            tooltip: 'Memory',
          ),
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: c != null && !_streaming ? _regenerate : null,
            color: kMuted,
            tooltip: 'Regenerate',
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: c != null && !_streaming ? _clearChat : null,
            color: kMuted,
            tooltip: 'Clear chat',
          ),
        ],
      ),
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: bgColors,
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: c == null
            ? Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: const [
                    Icon(Icons.chat_bubble_outline_rounded, color: kMuted, size: 44),
                    SizedBox(height: 12),
                    Text('Pick a character to start chatting',
                        style: TextStyle(color: kMuted, fontSize: 14)),
                  ],
                ),
              )
            : Column(
                children: [
                  Expanded(
                    child: Stack(
                      children: [
                        _MessageList(
                          history: _history,
                          streaming: _streaming,
                          streamingText: _streamingText,
                          char: c,
                          userName: ap.displayName,
                          scrollController: _scrollCtrl,
                          error: _error,
                          appearance: appearance,
                          onRetry: () {
                            setState(() => _error = null);
                            if (_history.isNotEmpty && _history.last.isUser) {
                              _generate();
                            } else {
                              _regenerate();
                            }
                          },
                        ),
                        if (_showMemory)
                          Positioned(
                            top: 0, bottom: 0, right: 0,
                            child: _MemoryPanel(
                              charId: c.id,
                              facts: _memFacts,
                              onChanged: () => setState(() {
                                _memFacts = StorageService.instance.loadMemory(c.id);
                              }),
                            ),
                          ),
                      ],
                    ),
                  ),
                  _InputBar(
                    controller: _input,
                    onSend: _send,
                    enabled: !_streaming,
                  ),
                ],
              ),
      ),
    );
  }
}

// ── _MessageList ──────────────────────────────────────────────────────────────

class _MessageList extends StatelessWidget {
  final List<ChatMessage> history;
  final bool streaming;
  final String streamingText;
  final Character char;
  final String userName;
  final ScrollController scrollController;
  final String? error;
  final VoidCallback onRetry;
  final ChatAppearance appearance;

  const _MessageList({
    required this.history,
    required this.streaming,
    required this.streamingText,
    required this.char,
    required this.userName,
    required this.scrollController,
    required this.onRetry,
    required this.appearance,
    this.error,
  });

  @override
  Widget build(BuildContext context) {
    final items = <Widget>[];
    for (final m in history) {
      items.add(_Bubble(message: m, char: char, userName: userName, appearance: appearance));
    }
    if (streaming && streamingText.isNotEmpty) {
      items.add(_Bubble(
        message: ChatMessage(role: 'assistant', content: streamingText),
        char: char,
        userName: userName,
        live: true,
        appearance: appearance,
      ));
    } else if (streaming) {
      items.add(_TypingIndicator(char: char));
    }
    if (error != null) {
      items.add(_ErrorBubble(error: error!, onRetry: onRetry));
    }

    return ListView.builder(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
      itemCount: items.length,
      itemBuilder: (_, i) => items[i],
    );
  }
}

// ── _Bubble ───────────────────────────────────────────────────────────────────

BorderRadius _bubbleRadius(bool isUser, BubbleStyle style) {
  switch (style) {
    case BubbleStyle.sharp:
      return BorderRadius.circular(6);
    case BubbleStyle.minimal:
      return BorderRadius.only(
        topLeft: const Radius.circular(14),
        topRight: const Radius.circular(14),
        bottomLeft: Radius.circular(isUser ? 14 : 2),
        bottomRight: Radius.circular(isUser ? 2 : 14),
      );
    case BubbleStyle.rounded:
    default:
      return BorderRadius.only(
        topLeft: const Radius.circular(18),
        topRight: const Radius.circular(18),
        bottomLeft: Radius.circular(isUser ? 18 : 5),
        bottomRight: Radius.circular(isUser ? 5 : 18),
      );
  }
}

class _Bubble extends StatelessWidget {
  final ChatMessage message;
  final Character char;
  final String userName;
  final bool live;
  final ChatAppearance appearance;

  const _Bubble({
    required this.message,
    required this.char,
    required this.userName,
    required this.appearance,
    this.live = false,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final maxW = MediaQuery.of(context).size.width * 0.78;
    final acc = accentFor(char.name);
    final radius = _bubbleRadius(isUser, appearance.bubbleStyle);

    // pick colors from palette
    final userColors = _bubblePalette[appearance.userBubbleColorIndex.clamp(0, _bubblePalette.length - 1)];
    final charColors = _bubblePalette[appearance.charBubbleColorIndex.clamp(0, _bubblePalette.length - 1)];

    final bubble = Container(
      constraints: BoxConstraints(maxWidth: maxW),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        gradient: isUser
            ? LinearGradient(colors: userColors, begin: Alignment.topLeft, end: Alignment.bottomRight)
            : LinearGradient(
                colors: [charColors[0].withOpacity(0.9), charColors[1]],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
        borderRadius: radius,
        border: isUser ? null : Border.all(color: acc.first.withOpacity(0.35), width: 0.8),
        boxShadow: isUser
            ? [BoxShadow(color: userColors[0].withOpacity(0.25), blurRadius: 10, offset: const Offset(0, 3))]
            : null,
      ),
      child: isUser
          ? SelectableText(
              message.content,
              style: TextStyle(color: kText, fontSize: appearance.fontSize, height: 1.45),
            )
          : _CaiText(text: message.content, fontSize: appearance.fontSize),
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isUser) ...[
            CharAvatar(name: char.name, path: char.avatar, size: 30, radius: 10),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(left: 4, right: 4, bottom: 3),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        isUser ? userName : char.name,
                        style: TextStyle(
                          color: isUser ? kPrimary2 : acc.first,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (live) ...[
                        const SizedBox(width: 6),
                        const SizedBox(
                          width: 8, height: 8,
                          child: CircularProgressIndicator(strokeWidth: 1.5, color: kGreen),
                        ),
                      ],
                    ],
                  ),
                ),
                bubble,
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── _CaiText — renders *action* in soft italic ────────────────────────────────

class _CaiText extends StatelessWidget {
  final String text;
  final double fontSize;
  const _CaiText({required this.text, this.fontSize = 15});

  List<InlineSpan> _parse() {
    final spans = <InlineSpan>[];
    int i = 0;
    while (i < text.length) {
      final star = text.indexOf('*', i);
      if (star == -1) {
        spans.add(TextSpan(text: text.substring(i)));
        break;
      }
      final end = text.indexOf('*', star + 1);
      if (end == -1) {
        spans.add(TextSpan(text: text.substring(i)));
        break;
      }
      if (star > i) spans.add(TextSpan(text: text.substring(i, star)));
      spans.add(TextSpan(
        text: text.substring(star + 1, end),
        style: const TextStyle(color: Color(0xFFB4A8FF), fontStyle: FontStyle.italic),
      ));
      i = end + 1;
    }
    return spans;
  }

  @override
  Widget build(BuildContext context) => SelectableText.rich(
        TextSpan(
          style: TextStyle(color: kText, fontSize: fontSize, height: 1.5),
          children: _parse(),
        ),
      );
}

class _TypingIndicator extends StatelessWidget {
  final Character char;
  const _TypingIndicator({required this.char});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          children: [
            CharAvatar(name: char.name, path: char.avatar, size: 30, radius: 10),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                color: kBubbleChar,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: kBorder, width: 0.8),
              ),
              child: const _Dots(),
            ),
          ],
        ),
      );
}

class _Dots extends StatefulWidget {
  const _Dots();
  @override
  State<_Dots> createState() => _DotsState();
}

class _DotsState extends State<_Dots> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat();

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _c,
        builder: (_, __) => Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            final t = ((_c.value * 3) - i).clamp(0.0, 1.0);
            final y = -4 * (1 - (2 * t - 1).abs());
            return Transform.translate(
              offset: Offset(0, y),
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 2.5),
                width: 7, height: 7,
                decoration: BoxDecoration(
                  color: kMuted.withOpacity(0.5 + 0.5 * (1 - (2 * t - 1).abs())),
                  shape: BoxShape.circle,
                ),
              ),
            );
          }),
        ),
      );
}

class _ErrorBubble extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;
  const _ErrorBubble({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 8, top: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kDanger.withOpacity(0.08),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: kDanger.withOpacity(0.35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: const [
                Icon(Icons.wifi_off_rounded, color: kDanger, size: 16),
                SizedBox(width: 8),
                Text("Couldn't reach the model",
                    style: TextStyle(color: kDanger, fontWeight: FontWeight.w600, fontSize: 13)),
              ],
            ),
            const SizedBox(height: 6),
            Text(error, style: const TextStyle(color: kTextSoft, fontSize: 13, height: 1.45)),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Retry'),
              style: OutlinedButton.styleFrom(
                foregroundColor: kDanger,
                side: BorderSide(color: kDanger.withOpacity(0.5)),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              ),
            ),
          ],
        ),
      );
}

// ── _InputBar ─────────────────────────────────────────────────────────────────

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSend;
  final bool enabled;

  const _InputBar({required this.controller, required this.onSend, required this.enabled});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        decoration: const BoxDecoration(
          color: kBg,
          border: Border(top: BorderSide(color: kBorder, width: 0.5)),
        ),
        child: SafeArea(
          top: false,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  maxLines: 5,
                  minLines: 1,
                  keyboardType: TextInputType.multiline,
                  textInputAction: TextInputAction.newline,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: InputDecoration(
                    hintText: enabled ? 'Message…' : 'Waiting for reply…',
                    filled: true,
                    fillColor: kSurface,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: const BorderSide(color: kBorder),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: const BorderSide(color: kPrimary, width: 1.2),
                    ),
                    disabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: const BorderSide(color: kBorder),
                    ),
                  ),
                  style: const TextStyle(color: kText, fontSize: 15),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: enabled ? onSend : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    gradient: enabled ? kGradient : null,
                    color: enabled ? null : kBorder,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(Icons.arrow_upward_rounded,
                      color: enabled ? Colors.white : kMuted, size: 22),
                ),
              ),
            ],
          ),
        ),
      );
}

// ── _MemoryPanel ──────────────────────────────────────────────────────────────

class _MemoryPanel extends StatefulWidget {
  final String charId;
  final List<String> facts;
  final VoidCallback onChanged;

  const _MemoryPanel({required this.charId, required this.facts, required this.onChanged});

  @override
  State<_MemoryPanel> createState() => _MemoryPanelState();
}

class _MemoryPanelState extends State<_MemoryPanel> {
  final _ctrl = TextEditingController();

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  void _add() {
    final text = _ctrl.text.trim();
    if (text.isEmpty) return;
    StorageService.instance.addMemoryFact(widget.charId, text);
    _ctrl.clear();
    widget.onChanged();
  }

  void _delete(int i) {
    StorageService.instance.deleteMemoryFact(widget.charId, i);
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) => Container(
    width: (MediaQuery.of(context).size.width * 0.72).clamp(220.0, 300.0).toDouble(),
    decoration: BoxDecoration(
      color: kSurface.withOpacity(0.97),
      border: const Border(left: BorderSide(color: kBorder, width: 0.5)),
      boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 20)],
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(12, 12, 12, 6),
          child: Text('MEMORY', style: TextStyle(color: kMuted, fontSize: 11, letterSpacing: 0.8, fontWeight: FontWeight.w700)),
        ),
        Expanded(
          child: widget.facts.isEmpty
              ? const Center(child: Text('No memories yet', style: TextStyle(color: kMuted, fontSize: 12)))
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  itemCount: widget.facts.length,
                  itemBuilder: (_, i) => Container(
                    margin: const EdgeInsets.only(bottom: 4),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    decoration: BoxDecoration(
                      color: kCard,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: kBorder),
                    ),
                    child: Row(
                      children: [
                        Expanded(child: Text(widget.facts[i], style: const TextStyle(color: kTextSoft, fontSize: 12.5, height: 1.35))),
                        GestureDetector(
                          onTap: () => _delete(i),
                          child: const Icon(Icons.close, size: 12, color: kMuted),
                        ),
                      ],
                    ),
                  ),
                ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  onSubmitted: (_) => _add(),
                  decoration: const InputDecoration(
                    hintText: 'Add memory…',
                    contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  ),
                  style: const TextStyle(color: kText, fontSize: 12),
                ),
              ),
              const SizedBox(width: 4),
              GestureDetector(
                onTap: _add,
                child: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(color: kPrimary.withOpacity(0.15), borderRadius: BorderRadius.circular(6)),
                  child: const Icon(Icons.add, size: 16, color: kPrimary),
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

// ── _AppearanceSheet ──────────────────────────────────────────────────────────

class _AppearanceSheet extends StatefulWidget {
  final ChatAppearance appearance;
  final ValueChanged<ChatAppearance> onChanged;
  const _AppearanceSheet({required this.appearance, required this.onChanged});

  @override
  State<_AppearanceSheet> createState() => _AppearanceSheetState();
}

class _AppearanceSheetState extends State<_AppearanceSheet> {
  late ChatAppearance _a;

  @override
  void initState() {
    super.initState();
    _a = widget.appearance;
  }

  void _update(ChatAppearance next) {
    setState(() => _a = next);
    widget.onChanged(next);
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (_, ctrl) => Container(
        decoration: const BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          border: Border(top: BorderSide(color: kBorder)),
        ),
        child: Column(
          children: [
            const SizedBox(height: 8),
            Container(width: 36, height: 4, decoration: BoxDecoration(color: kBorder, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: Row(children: [
                Icon(Icons.palette_outlined, color: kPrimary, size: 20),
                SizedBox(width: 8),
                Text('Appearance', style: TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 18)),
              ]),
            ),
            const SizedBox(height: 4),
            Expanded(
              child: ListView(
                controller: ctrl,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                children: [
                  // ── Bubble style ───────────────────────────────────────────
                  _SectionLabel('Bubble Style'),
                  const SizedBox(height: 8),
                  Row(
                    children: BubbleStyle.values.map((s) {
                      final active = _a.bubbleStyle == s;
                      final label = s.name[0].toUpperCase() + s.name.substring(1);
                      return Expanded(
                        child: GestureDetector(
                          onTap: () => _update(_a.copyWith(bubbleStyle: s)),
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 150),
                            margin: const EdgeInsets.only(right: 8),
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            decoration: BoxDecoration(
                              color: active ? kPrimary.withOpacity(0.18) : kCard,
                              borderRadius: BorderRadius.circular(s == BubbleStyle.sharp ? 4 : s == BubbleStyle.rounded ? 14 : 10),
                              border: Border.all(color: active ? kPrimary : kBorder, width: active ? 1.5 : 1),
                            ),
                            child: Column(
                              children: [
                                // mini preview
                                Container(
                                  width: 48, height: 18,
                                  decoration: BoxDecoration(
                                    gradient: const LinearGradient(colors: [kPrimary, kPrimary2]),
                                    borderRadius: BorderRadius.circular(s == BubbleStyle.sharp ? 2 : s == BubbleStyle.rounded ? 10 : 6),
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(label, style: TextStyle(color: active ? kPrimary : kMuted, fontSize: 12, fontWeight: FontWeight.w600)),
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 20),

                  // ── Background ─────────────────────────────────────────────
                  _SectionLabel('Background'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8, runSpacing: 8,
                    children: BackgroundPreset.values.map((p) {
                      final colors = _bgPresets[p]!;
                      final active = _a.background == p;
                      return GestureDetector(
                        onTap: () => _update(_a.copyWith(background: p)),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 150),
                          width: 64, height: 64,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(colors: colors, begin: Alignment.topLeft, end: Alignment.bottomRight),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: active ? kPrimary : kBorder,
                              width: active ? 2 : 1,
                            ),
                            boxShadow: active ? [BoxShadow(color: kPrimary.withOpacity(0.4), blurRadius: 8)] : null,
                          ),
                          child: active
                              ? const Icon(Icons.check_rounded, color: Colors.white, size: 22)
                              : Center(
                                  child: Text(
                                    _bgLabels[p] ?? '',
                                    style: const TextStyle(color: Colors.white70, fontSize: 9, fontWeight: FontWeight.w600),
                                    textAlign: TextAlign.center,
                                  ),
                                ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 20),

                  // ── Bubble colours ─────────────────────────────────────────
                  _SectionLabel('Your Bubble Color'),
                  const SizedBox(height: 8),
                  _ColorRow(
                    selected: _a.userBubbleColorIndex,
                    onSelect: (i) => _update(_a.copyWith(userBubbleColorIndex: i)),
                  ),
                  const SizedBox(height: 14),
                  _SectionLabel('Character Bubble Color'),
                  const SizedBox(height: 8),
                  _ColorRow(
                    selected: _a.charBubbleColorIndex,
                    onSelect: (i) => _update(_a.copyWith(charBubbleColorIndex: i)),
                  ),
                  const SizedBox(height: 20),

                  // ── Font size ──────────────────────────────────────────────
                  _SectionLabel('Font Size'),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const Text('A', style: TextStyle(color: kMuted, fontSize: 12)),
                      Expanded(
                        child: Slider(
                          value: _a.fontSize,
                          min: 12, max: 20, divisions: 8,
                          activeColor: kPrimary,
                          inactiveColor: kBorder,
                          onChanged: (v) => _update(_a.copyWith(fontSize: v)),
                        ),
                      ),
                      const Text('A', style: TextStyle(color: kMuted, fontSize: 20)),
                    ],
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ColorRow extends StatelessWidget {
  final int selected;
  final ValueChanged<int> onSelect;
  const _ColorRow({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 44,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          itemCount: _bubblePalette.length,
          itemBuilder: (_, i) {
            final active = selected == i;
            return GestureDetector(
              onTap: () => onSelect(i),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                width: 44, height: 44,
                margin: const EdgeInsets.only(right: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: _bubblePalette[i],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: active ? kPrimary : kBorder,
                    width: active ? 2.5 : 1.5,
                  ),
                  boxShadow: active ? [BoxShadow(color: kPrimary.withOpacity(0.4), blurRadius: 6)] : null,
                ),
                child: active ? const Icon(Icons.check_rounded, color: Colors.white, size: 18) : null,
              ),
            );
          },
        ),
      );
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);
  @override
  Widget build(BuildContext context) => Text(
        text.toUpperCase(),
        style: const TextStyle(color: kMuted, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8),
      );
}

// ── _PersonaSwitcherSheet ─────────────────────────────────────────────────────

class _PersonaSwitcherSheet extends StatelessWidget {
  final List<Persona> personas;
  final String activeId;
  final ValueChanged<String> onSelect;
  final VoidCallback onDeactivate;

  const _PersonaSwitcherSheet({
    required this.personas,
    required this.activeId,
    required this.onSelect,
    required this.onDeactivate,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        border: Border(top: BorderSide(color: kBorder)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 8),
          Container(width: 36, height: 4, decoration: BoxDecoration(color: kBorder, borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 16),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Row(children: [
              Icon(Icons.person_pin_outlined, color: kPrimary, size: 20),
              SizedBox(width: 8),
              Text('Switch Persona', style: TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 18)),
            ]),
          ),
          const SizedBox(height: 8),
          if (personas.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text('No personas yet — create one in the Personas tab.',
                  style: TextStyle(color: kMuted), textAlign: TextAlign.center),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 360),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
                shrinkWrap: true,
                children: [
                  // "None" option
                  _PersonaTile(
                    name: 'None (use display name)',
                    subtitle: 'No persona active',
                    active: activeId.isEmpty,
                    onTap: () {
                      onDeactivate();
                      Navigator.pop(context);
                    },
                  ),
                  const Divider(color: kBorder, height: 16),
                  ...personas.map((p) => _PersonaTile(
                        name: p.name,
                        subtitle: p.personality.isNotEmpty
                            ? p.personality
                            : (p.backstory.isNotEmpty ? p.backstory : 'No description'),
                        active: activeId == p.id,
                        avatarSeed: p.name,
                        onTap: () {
                          onSelect(p.id);
                          Navigator.pop(context);
                        },
                      )),
                ],
              ),
            ),
          SizedBox(height: MediaQuery.of(context).padding.bottom + 8),
        ],
      ),
    );
  }
}

class _PersonaTile extends StatelessWidget {
  final String name;
  final String subtitle;
  final bool active;
  final VoidCallback onTap;
  final String? avatarSeed;

  const _PersonaTile({
    required this.name,
    required this.subtitle,
    required this.active,
    required this.onTap,
    this.avatarSeed,
  });

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          margin: const EdgeInsets.only(bottom: 6),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: active ? kPrimary.withOpacity(0.12) : kCard,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: active ? kPrimary : kBorder, width: active ? 1.5 : 1),
          ),
          child: Row(
            children: [
              if (avatarSeed != null) ...[
                CharAvatar(name: avatarSeed!, size: 36, radius: 12),
                const SizedBox(width: 12),
              ] else ...[
                Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(color: kBorder, borderRadius: BorderRadius.circular(12)),
                  child: const Icon(Icons.do_not_disturb_alt_outlined, color: kMuted, size: 18),
                ),
                const SizedBox(width: 12),
              ],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, style: TextStyle(color: active ? kPrimary : kText, fontWeight: FontWeight.w600, fontSize: 14)),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(color: kMuted, fontSize: 12),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              if (active) const Icon(Icons.check_circle_rounded, color: kPrimary, size: 20),
            ],
          ),
        ),
      );
}

// ── _HistorySheet ─────────────────────────────────────────────────────────────

class _HistorySheet extends StatefulWidget {
  final Character char;
  final ValueChanged<ChatSession> onLoad;
  final VoidCallback? onSaveCurrent;

  const _HistorySheet({
    required this.char,
    required this.onLoad,
    this.onSaveCurrent,
  });

  @override
  State<_HistorySheet> createState() => _HistorySheetState();
}

class _HistorySheetState extends State<_HistorySheet> {
  late List<ChatSession> _sessions;

  @override
  void initState() {
    super.initState();
    _sessions = StorageService.instance.loadSessions(widget.char.id);
  }

  void _delete(String id) {
    StorageService.instance.deleteSession(id);
    setState(() => _sessions = StorageService.instance.loadSessions(widget.char.id));
  }

  String _formatDate(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inDays == 0) return 'Today';
    if (diff.inDays == 1) return 'Yesterday';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.month}/${dt.day}/${dt.year}';
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.65,
      minChildSize: 0.35,
      maxChildSize: 0.92,
      builder: (_, ctrl) => Container(
        decoration: const BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          border: Border(top: BorderSide(color: kBorder)),
        ),
        child: Column(
          children: [
            const SizedBox(height: 8),
            Container(width: 36, height: 4, decoration: BoxDecoration(color: kBorder, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  const Icon(Icons.history_rounded, color: kPrimary, size: 20),
                  const SizedBox(width: 8),
                  Text('Chat History — ${widget.char.name}',
                      style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 18)),
                  const Spacer(),
                  if (widget.onSaveCurrent != null)
                    TextButton.icon(
                      onPressed: () {
                        widget.onSaveCurrent!();
                        setState(() => _sessions = StorageService.instance.loadSessions(widget.char.id));
                      },
                      icon: const Icon(Icons.save_alt_rounded, size: 16),
                      label: const Text('Save'),
                      style: TextButton.styleFrom(foregroundColor: kPrimary, textStyle: const TextStyle(fontSize: 13)),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 4),
            Expanded(
              child: _sessions.isEmpty
                  ? Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: const [
                        Icon(Icons.history_rounded, color: kMuted, size: 40),
                        SizedBox(height: 12),
                        Text('No saved chats yet.',
                            style: TextStyle(color: kMuted, fontSize: 14)),
                        SizedBox(height: 4),
                        Text('Tap Save to store the current chat.',
                            style: TextStyle(color: kMuted, fontSize: 12)),
                      ],
                    )
                  : ListView.builder(
                      controller: ctrl,
                      padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
                      itemCount: _sessions.length,
                      itemBuilder: (_, i) {
                        final s = _sessions[i];
                        return Dismissible(
                          key: Key(s.id),
                          direction: DismissDirection.endToStart,
                          background: Container(
                            alignment: Alignment.centerRight,
                            padding: const EdgeInsets.only(right: 16),
                            decoration: BoxDecoration(
                              color: kDanger.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: const Icon(Icons.delete_outline, color: kDanger),
                          ),
                          onDismissed: (_) => _delete(s.id),
                          child: GestureDetector(
                            onTap: () {
                              widget.onLoad(s);
                              Navigator.pop(context);
                            },
                            child: Container(
                              margin: const EdgeInsets.only(bottom: 8),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: kCard,
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(color: kBorder),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(s.title,
                                            style: const TextStyle(color: kText, fontWeight: FontWeight.w600, fontSize: 14),
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis),
                                        const SizedBox(height: 4),
                                        Text(
                                          '${s.messages.length} messages · ${_formatDate(s.createdAt)}',
                                          style: const TextStyle(color: kMuted, fontSize: 12),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  const Icon(Icons.chevron_right_rounded, color: kMuted, size: 18),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
