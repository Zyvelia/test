// chat_screen.dart — streaming chat with memory sidebar, appearance menu,
//                    in-chat persona switcher, and chat history drawer

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final _input = TextEditingController();
  final _scrollCtrl = ScrollController();
  List<ChatMessage> _history = [];
  bool _streaming = false;
  bool _stopRequested = false;
  bool? _connectionOk;
  String _streamingText = '';
  String? _error;
  bool _showMemory = false;
  List<String> _memFacts = [];
  StoryState _storyState = StoryState();
  CharacterProfileMemory _characterProfile = const CharacterProfileMemory();
  String? _storyStateKey;
  String? _loadedCharId;
  SessionWallet? _wallet;
  bool _showWallet = false;
  RelationshipState _relationship = RelationshipState();
  ChatAppearance? _characterAppearance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkConnection();
  }

  Future<void> _checkConnection() async {
    final settings = context.read<AppProvider>().settings;
    final error = await OllamaService.instance.testConnection(settings.ollamaUrl);
    if (mounted) setState(() => _connectionOk = error == null);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      final c = context.read<AppProvider>().activeChar;
      if (c != null) {
        final snapshot = List<ChatMessage>.from(_history);
        if (_streamingText.trim().isNotEmpty) {
          snapshot.add(ChatMessage(role: 'assistant', content: _parseWalletTags(_streamingText.trim())));
        }
        StorageService.instance.saveChat(c.id, snapshot);
      }
    } else if (state == AppLifecycleState.resumed) {
      _checkConnection();
    }
  }

  void _stopGeneration() {
    if (!_streaming) return;
    setState(() => _stopRequested = true);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _input.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _loadChat() {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) { setState(() => _history = []); return; }
    final store = StorageService.instance;
    var history = store.loadChat(c.id);
    if (history.isEmpty && c.greeting.isNotEmpty) {
      history = [ChatMessage(role: 'assistant', content: c.greeting)];
      store.saveChat(c.id, history);
    }
    _memFacts = store.loadMemory(c.id);
    final pinnedFacts = store.loadPinnedMemory(c.id);
    _memFacts.sort((a, b) { final ap = pinnedFacts.contains(a) ? 0 : 1; final bp = pinnedFacts.contains(b) ? 0 : 1; return ap.compareTo(bp); });
    _relationship = store.loadRelationship(c.id);
    _characterAppearance = store.loadCharacterAppearance(c.id);
    _storyStateKey = '${c.id}_active';
    _storyState = store.loadStoryState(_storyStateKey!);
    // Migrate continuity saved by older versions from per-character storage.
    if (_storyState.isEmpty) {
      final legacy = store.loadStoryState(c.id);
      if (!legacy.isEmpty) { _storyState = legacy; store.saveStoryState(_storyStateKey!, legacy); }
    }
    _characterProfile = store.loadCharacterProfile(c.id);
    // init fresh wallet each session load
    final cname = c.currencyName.trim();
    final csym  = c.currencySymbol.trim();
    _wallet = SessionWallet(
      currencyName:   cname.isNotEmpty ? cname : 'gold',
      currencySymbol: csym.isNotEmpty  ? csym  : '🪙',
    );
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
    final c = context.read<AppProvider>().activeChar;
    if (c == null || _input.text.trim().isEmpty || _streaming) return;
    final userMsg = _input.text.trim();
    _input.clear();
    if (context.read<AppProvider>().settings.hapticOnSend) {
      HapticFeedback.lightImpact();
    }
    _history.add(ChatMessage(role: 'user', content: userMsg));
    StorageService.instance.saveChat(c.id, _history);
    await _generate(extractAfter: true);
  }

  Future<void> _regenerate() async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null || _streaming) return;
    if (_history.isNotEmpty) {
      StorageService.instance.saveSession(c.id, c.name, List<ChatMessage>.from(_history), storyState: _storyState);
    }
    while (_history.isNotEmpty && _history.last.isAssistant) {
      _history.removeLast();
    }
    StorageService.instance.saveChat(c.id, _history);
    setState(() {});
    if (_history.isNotEmpty) await _generate();
  }

  Future<void> _editMessage(int index) async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null || _streaming || index < 0 || index >= _history.length) return;
    final original = _history[index];
    final controller = TextEditingController(text: original.content);
    final edited = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(original.isUser ? 'Edit your message' : 'Edit character reply'),
        content: SizedBox(width: 520, child: TextField(
          controller: controller, autofocus: true, minLines: 3, maxLines: 10,
          decoration: const InputDecoration(hintText: 'Message text'),
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Save')),
        ],
      ),
    );
    controller.dispose();
    if (edited == null || edited.isEmpty || !mounted) return;
    StorageService.instance.saveSession(c.id, c.name, List<ChatMessage>.from(_history), storyState: _storyState);
    setState(() {
      _history[index] = ChatMessage(role: original.role, content: edited, timestamp: original.timestamp);
      // Editing an earlier user message starts a new branch from that point.
      // Later turns are retained in the snapshot created above.
      if (original.isUser) _history = _history.take(index + 1).toList();
    });
    StorageService.instance.saveChat(c.id, _history);
    if (original.isUser) {
      await _generate(extractAfter: true);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Reply edited. The original conversation is preserved in chat history.')));
    }
  }

  void _branchFromMessage(int index) {
    final c = context.read<AppProvider>().activeChar;
    if (c == null || _streaming || index < 0 || index >= _history.length) return;
    StorageService.instance.saveSession(c.id, c.name, List<ChatMessage>.from(_history), storyState: _storyState);
    setState(() => _history = _history.take(index + 1).toList());
    StorageService.instance.saveChat(c.id, _history);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Alternate timeline created. The original is in chat history.')));
    _scrollBottom();
  }

  Future<void> _generate({bool extractAfter = false}) async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    final ap = context.read<AppProvider>();
    final s = ap.settings;
    final persona = ap.activePersona;

    setState(() { _streaming = true; _stopRequested = false; _streamingText = ''; _error = null; });
    _scrollBottom();

    // wallet context appended to system prompt (not a second system message —
    // consecutive system messages confuse many Ollama models)
    final walletCtx = _wallet != null
        ? '\n\n<<WALLET_CONTEXT>>\n'
          'Currency: ${_wallet!.currencyName} (${_wallet!.currencySymbol})\n'
          '${c.name} balance: ${_wallet!.charBalance} ${_wallet!.currencyName}\n'
          'User balance: ${_wallet!.userBalance} ${_wallet!.currencyName}\n'
          'To move money silently embed tags in your reply (stripped before display):\n'
          '  [EARN:N:reason]       — user earns N\n'
          '  [SPEND:N:reason]      — user spends N\n'
          '  [CHAR_EARN:N:reason]  — ${c.name} earns N\n'
          '  [CHAR_SPEND:N:reason] — ${c.name} spends N\n'
          'Use them naturally when the story calls for it. Never mention the tags.\n'
          'If currency name/symbol are not yet defined, pick ones fitting the world and use them consistently.\n'
          '<<END_WALLET_CONTEXT>>'
        : '';
    final baseSystemPrompt = OllamaService.instance.buildSystemPrompt(c, s, persona, _memFacts, storyState: _storyState, characterProfile: _characterProfile) + '\n\nRELATIONSHIP TRACKER (user-editable continuity; do not change scores yourself):\nFamiliarity: ${_relationship.familiarity}/100\nTrust: ${_relationship.trust}/100\nAffection: ${_relationship.affection}/100\nRivalry: ${_relationship.rivalry}/100\nRelationship notes: ${_relationship.notes}\nShared events: ${_relationship.sharedEvents.join('; ')}\nTreat these values as continuity context, not as a command to force romance or conflict.';
    final systemPrompt = walletCtx.isNotEmpty ? baseSystemPrompt + walletCtx : baseSystemPrompt;

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
        model: c.modelOverride.trim().isNotEmpty ? c.modelOverride.trim() : s.model,
        messages: messages,
        maxReplyTokens: s.maxReplyTokens,
      )) {
        if (!mounted) return;
        if (_stopRequested) break;
        setState(() => _streamingText += chunk);
        _scrollBottom();
      }

      final raw = _streamingText.trim();
      // parse and strip silent wallet tags before displaying
      final response = _parseWalletTags(raw);
      if (response.isEmpty && !_stopRequested) {
        throw Exception('The model returned an empty reply. Try again, or pick a different model in Settings.');
      }
      if (response.isNotEmpty) _history.add(ChatMessage(role: 'assistant', content: response));
      StorageService.instance.saveChat(c.id, _history);
      if (!mounted) return;
      setState(() { _streaming = false; _stopRequested = false; _streamingText = ''; });
      _scrollBottom();

      if (extractAfter && _history.where((m) => m.isUser).length % 3 == 0) {
        _updateStoryState();
      }
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
        _error = _stopRequested ? null : OllamaService.friendlyError(e);
        _stopRequested = false;
      });
      _scrollBottom();
    }
  }

  void _clearChat() {
    final c = context.read<AppProvider>().activeChar;
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
              StorageService.instance.clearStoryState(_storyStateKey ?? '${c.id}_active');
              StorageService.instance.clearStoryState(c.id); // remove legacy per-character state so it is not migrated back
              _storyState = StoryState();
              Navigator.pop(context);
              _loadChat();
            },
            child: const Text('Clear', style: TextStyle(color: kDanger)),
          ),
        ],
      ),
    );
  }

  // Strips [EARN:N:label], [SPEND:N:label], [CHAR_EARN:N:label], [CHAR_SPEND:N:label]
  // from AI output silently and applies them to the wallet.
  // label is optional. owner defaults to 'user' for EARN/SPEND, 'char' for CHAR_*.
  String _parseWalletTags(String text) {
    if (_wallet == null) return text;
    final pattern = RegExp(
      r'\[(EARN|SPEND|CHAR_EARN|CHAR_SPEND):(\d+)(?::([^\]]*))?\]',
      caseSensitive: false,
    );
    final result = text.replaceAllMapped(pattern, (m) {
      final tag    = m.group(1)!.toUpperCase();
      final amount = int.tryParse(m.group(2) ?? '0') ?? 0;
      final label  = m.group(3) ?? '';
      final owner  = tag.startsWith('CHAR') ? 'char' : 'user';
      final delta  = (tag == 'SPEND' || tag == 'CHAR_SPEND') ? -amount : amount;
      _wallet!.apply(WalletEntry(
        time: DateTime.now(),
        owner: owner,
        amount: delta,
        label: label,
      ));
      return ''; // strip from visible text
    });
    // rebuild setState so wallet UI updates
    WidgetsBinding.instance.addPostFrameCallback((_) { if (mounted) setState(() {}); });
    return result.trim();
  }

  void _updateStoryState() async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    final s = context.read<AppProvider>().settings;
    final selectedModel = c.modelOverride.trim().isNotEmpty ? c.modelOverride.trim() : s.model;
    final updated = await OllamaService.instance.updateStoryState(
      baseUrl: s.ollamaUrl,
      model: selectedModel,
      charName: c.name,
      current: _storyState,
      recentMessages: List<ChatMessage>.from(_history),
    );
    if (mounted && updated != null) {
      StorageService.instance.saveStoryState(_storyStateKey ?? '${c.id}_active', updated);
      setState(() { _storyState = StorageService.instance.loadStoryState(_storyStateKey ?? '${c.id}_active'); });
    }
    final relationship = await OllamaService.instance.updateRelationshipState(
      baseUrl: s.ollamaUrl,
      model: c.modelOverride.trim().isNotEmpty ? c.modelOverride.trim() : s.model,
      charName: c.name,
      current: _relationship,
      recentMessages: List<ChatMessage>.from(_history),
    );
    if (mounted && relationship != null) {
      StorageService.instance.saveRelationship(c.id, relationship);
      setState(() => _relationship = relationship);
    }
    // Run personal-fact extraction after continuity/relationship updates so local
    // Ollama requests do not compete with one another.
    await _extractMemory();
  }

  Future<void> _extractMemory() async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    final s = context.read<AppProvider>().settings;
    final facts = await OllamaService.instance.extractMemory(
      baseUrl: s.ollamaUrl,
      model: c.modelOverride.trim().isNotEmpty ? c.modelOverride.trim() : s.model,
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
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _HistorySheet(
        char: c,
        onLoad: (session) {
          final restoredState = StorageService.instance.loadStoryState(session.id);
          final sessionState = !restoredState.isEmpty ? restoredState : (session.storyState ?? StoryState());
          setState(() { _history = List.from(session.messages); _storyStateKey = '${c.id}_active'; _storyState = sessionState; });
          StorageService.instance.saveStoryState('${c.id}_active', sessionState);
          StorageService.instance.saveChat(c.id, _history);
          _scrollBottom();
        },
        onSaveCurrent: _history.isNotEmpty ? () {
          StorageService.instance.saveSession(c.id, c.name, _history, storyState: _storyState);
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Chat saved to history')),
          );
        } : null,
      ),
    );
  }

  void _openTimeline() {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    final state = StorageService.instance.loadStoryState(_storyStateKey ?? '${c.id}_active');
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => SafeArea(
        child: Container(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.78),
          decoration: const BoxDecoration(color: kSurface, borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
          padding: const EdgeInsets.all(18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Expanded(child: Text('Story timeline', style: TextStyle(color: kText, fontSize: 19, fontWeight: FontWeight.w800))),
              IconButton(tooltip: 'Edit continuity', onPressed: () { Navigator.pop(ctx); setState(() => _showMemory = true); }, icon: const Icon(Icons.edit_note, color: kPrimary)),
            ]),
            Text('Updated ${state.updatedAt.millisecondsSinceEpoch == 0 ? 'not yet' : TimeOfDay.fromDateTime(state.updatedAt).format(ctx)}', style: const TextStyle(color: kMuted, fontSize: 11)),
            const SizedBox(height: 12),
            Expanded(child: ListView(children: [
              _timelineSection('Current scene', state.currentScene),
              _timelineSection('Character state', state.characterState),
              _timelineSection('Relationship dynamic', state.relationshipState),
              _timelineSection('Continuity notes', state.continuityNotes),
              _timelineListSection('Key events', state.keyEvents, Icons.history),
              _timelineListSection('Open threads', state.openThreads, Icons.pending_actions),
              if (state.isEmpty) const Padding(padding: EdgeInsets.symmetric(vertical: 30), child: Center(child: Text('No timeline entries yet. Keep chatting; continuity is updated periodically.', textAlign: TextAlign.center, style: TextStyle(color: kMuted)))),
            ])),
          ]),
        ),
      ),
    );
  }

  Widget _timelineSection(String title, String value) => value.trim().isEmpty
      ? const SizedBox.shrink()
      : Padding(padding: const EdgeInsets.only(bottom: 12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title.toUpperCase(), style: const TextStyle(color: kPrimary, fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.6)),
          const SizedBox(height: 4), Text(value, style: const TextStyle(color: kTextSoft, fontSize: 13, height: 1.4)),
        ]));

  Widget _timelineListSection(String title, List<String> items, IconData icon) => items.isEmpty
      ? const SizedBox.shrink()
      : Padding(padding: const EdgeInsets.only(bottom: 12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title.toUpperCase(), style: const TextStyle(color: kPrimary, fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.6)),
          const SizedBox(height: 5),
          ...items.reversed.map((item) => Padding(padding: const EdgeInsets.only(bottom: 6), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, size: 15, color: kMuted), const SizedBox(width: 8), Expanded(child: Text(item, style: const TextStyle(color: kTextSoft, fontSize: 12, height: 1.35))),
          ]))),
        ]));

  void _openRelationship() {
    final c = context.read<AppProvider>().activeChar;
    if (c == null) return;
    showModalBottomSheet<RelationshipState>(
      context: context, isScrollControlled: true, backgroundColor: Colors.transparent,
      builder: (_) => _RelationshipSheet(charName: c.name, initial: StorageService.instance.loadRelationship(c.id)),
    ).then((value) {
      if (value == null || !mounted) return;
      StorageService.instance.saveRelationship(c.id, value);
      setState(() => _relationship = value);
    });
  }

  Future<void> _openRewind() async {
    final c = context.read<AppProvider>().activeChar;
    if (c == null || _history.isEmpty) return;
    final choice = await showModalBottomSheet<int>(
      context: context, backgroundColor: Colors.transparent,
      builder: (ctx) => SafeArea(child: Container(
        decoration: const BoxDecoration(color: kSurface, borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
        padding: const EdgeInsets.all(18),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Rewind or branch', style: TextStyle(color: kText, fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          const Text('The current conversation is saved as a snapshot before rewinding.', style: TextStyle(color: kMuted, fontSize: 12)),
          const SizedBox(height: 12),
          ...List.generate(_history.length, (i) {
            final m = _history[i];
            final preview = m.content.replaceAll('\n', ' ');
            return ListTile(dense: true, contentPadding: EdgeInsets.zero,
              leading: Icon(m.isUser ? Icons.person_outline : Icons.smart_toy_outlined, color: m.isUser ? kCyan : kPrimary),
              title: Text('${i + 1}. ${m.isUser ? context.read<AppProvider>().displayName : c.name}', style: const TextStyle(color: kText, fontSize: 12)),
              subtitle: Text(preview.length > 72 ? '${preview.substring(0, 72)}…' : preview, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMuted, fontSize: 11)),
              onTap: () => Navigator.pop(ctx, i),
            );
          }),
        ]),
      )),
    );
    if (choice == null || !mounted) return;
    StorageService.instance.saveSession(c.id, c.name, List<ChatMessage>.from(_history), storyState: _storyState);
    setState(() { _history = _history.take(choice + 1).toList(); });
    StorageService.instance.saveChat(c.id, _history);
    _scrollBottom();
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Rewound. The previous timeline is preserved in chat history.')));
  }

  // ── Appearance sheet ──────────────────────────────────────────────────────────

  void _openAppearance() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AppearanceSheet(
        appearance: _characterAppearance ?? context.read<AppProvider>().appearance,
        onChanged: (a) {
          final char = context.read<AppProvider>().activeChar;
          if (char != null) { StorageService.instance.saveCharacterAppearance(char.id, a); setState(() => _characterAppearance = a); }
        },
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
        activeId: context.read<AppProvider>().activePersonaId,
        onSelect: (id) => context.read<AppProvider>().setActivePersona(id),
        onDeactivate: () => context.read<AppProvider>().deactivatePersona(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ap = context.watch<AppProvider>();
    final c = ap.activeChar;

    // Detect character switch here — watch() guarantees a rebuild whenever
    // activeChar changes, so this fires reliably where didChangeDependencies did not.
    if (c?.id != _loadedCharId && !_streaming) {
      _loadedCharId = c?.id;
      _error = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _loadChat();
      });
    }
    final persona = ap.activePersona;
    final appearance = _characterAppearance ?? ap.appearance;

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
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 5),
            child: Tooltip(
              message: _connectionOk == null ? 'Checking Ollama connection…' : (_connectionOk! ? 'Ollama connected' : 'Ollama disconnected'),
              child: Center(child: Container(
                width: 9, height: 9,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _connectionOk == null ? kMuted : (_connectionOk! ? kGreen : kDanger),
                  boxShadow: [BoxShadow(color: (_connectionOk == true ? kGreen : (_connectionOk == false ? kDanger : kMuted)).withValues(alpha: 0.35), blurRadius: 5)],
                ),
              )),
            ),
          ),
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
            icon: Icon(_showWallet ? Icons.account_balance_wallet : Icons.account_balance_wallet_outlined),
            onPressed: c == null ? null : () => setState(() => _showWallet = !_showWallet),
            color: _showWallet ? kAmber : kMuted,
            tooltip: 'Wallet',
          ),
          IconButton(
            icon: const Icon(Icons.favorite_border_rounded),
            onPressed: c == null ? null : _openRelationship,
            color: kPrimary2,
            tooltip: 'Relationship',
          ),
          IconButton(
            icon: const Icon(Icons.alt_route_rounded),
            onPressed: c != null && !_streaming ? _openRewind : null,
            color: kMuted,
            tooltip: 'Rewind / branch',
          ),
          IconButton(
            icon: const Icon(Icons.timeline_rounded),
            onPressed: c == null ? null : _openTimeline,
            color: kMuted,
            tooltip: 'Story timeline',
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
                    child: GestureDetector(
                      behavior: HitTestBehavior.translucent,
                      onTap: () => FocusScope.of(context).unfocus(),
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
                          onEditMessage: _editMessage,
                          onBranchFromMessage: _branchFromMessage,
                        ),
                        if (_showMemory)
                          Positioned(
                            top: 0, bottom: 0, right: 0,
                            child: _MemoryPanel(
                              charId: c.id,
                              storyStateKey: _storyStateKey ?? '${c.id}_active',
                              facts: _memFacts,
                              profile: _characterProfile,
                              onChanged: () => setState(() {
                                _memFacts = StorageService.instance.loadMemory(c.id);
                                _characterProfile = StorageService.instance.loadCharacterProfile(c.id);
                                _storyState = StorageService.instance.loadStoryState(_storyStateKey ?? '${c.id}_active');
                              }),
                            ),
                          ),
                        if (_showWallet && _wallet != null)
                          Positioned(
                            top: 0, bottom: 0, right: 0,
                            child: _WalletPanel(
                              wallet: _wallet!,
                              charName: c.name,
                              onManualEntry: (entry) => setState(() => _wallet!.apply(entry)),
                            ),
                          ),
                      ],
                    ),
                    ),
                  ),
                  _InputBar(
                    controller: _input,
                    onSend: _send,
                    enabled: !_streaming,
                    streaming: _streaming,
                    onStop: _stopGeneration,
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
  final ValueChanged<int> onEditMessage;
  final ValueChanged<int> onBranchFromMessage;
  final ChatAppearance appearance;

  const _MessageList({
    required this.history,
    required this.streaming,
    required this.streamingText,
    required this.char,
    required this.userName,
    required this.scrollController,
    required this.onRetry,
    required this.onEditMessage,
    required this.onBranchFromMessage,
    required this.appearance,
    this.error,
  });

  @override
  Widget build(BuildContext context) {
    final items = <Widget>[];
    for (var i = 0; i < history.length; i++) {
      items.add(_Bubble(
        message: history[i], char: char, userName: userName, appearance: appearance,
        messageIndex: i, onEdit: onEditMessage, onBranch: onBranchFromMessage,
      ));
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
  final int messageIndex;
  final ValueChanged<int>? onEdit;
  final ValueChanged<int>? onBranch;

  const _Bubble({
    required this.message,
    required this.char,
    required this.userName,
    required this.appearance,
    this.live = false,
    this.messageIndex = -1,
    this.onEdit,
    this.onBranch,
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
                colors: [charColors[0].withValues(alpha: 0.9), charColors[1]],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
        borderRadius: radius,
        border: isUser ? null : Border.all(color: acc.first.withValues(alpha: 0.35), width: 0.8),
        boxShadow: isUser
            ? [BoxShadow(color: userColors[0].withValues(alpha: 0.25), blurRadius: 10, offset: const Offset(0, 3))]
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
                GestureDetector(
                  onLongPress: () async {
                    await Clipboard.setData(ClipboardData(text: message.content));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                        content: Text('Message copied'),
                        duration: Duration(milliseconds: 1200),
                        behavior: SnackBarBehavior.floating,
                      ));
                    }
                  },
                  child: bubble,
                ),
                Padding(
                  padding: const EdgeInsets.only(left: 4, right: 0, top: 1),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Text(
                      TimeOfDay.fromDateTime(message.timestamp).format(context),
                      style: const TextStyle(color: kMuted, fontSize: 10),
                    ),
                    if (!live && messageIndex >= 0) PopupMenuButton<String>(
                      tooltip: 'Message actions',
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                      iconSize: 15,
                      icon: const Icon(Icons.more_horiz, color: kMuted),
                      onSelected: (action) {
                        if (action == 'edit') onEdit?.call(messageIndex);
                        if (action == 'branch') onBranch?.call(messageIndex);
                      },
                      itemBuilder: (_) => const [
                        PopupMenuItem(value: 'edit', child: ListTile(dense: true, leading: Icon(Icons.edit_outlined), title: Text('Edit message'))),
                        PopupMenuItem(value: 'branch', child: ListTile(dense: true, leading: Icon(Icons.alt_route), title: Text('Branch from here'))),
                      ],
                    ),
                  ]),
                ),
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
    var i = 0;
    while (i < text.length) {
      // Handle **bold** before *action* so paired delimiters are not misread.
      if (text.startsWith('**', i)) {
        final end = text.indexOf('**', i + 2);
        if (end >= 0) {
          spans.add(TextSpan(
            text: text.substring(i + 2, end),
            style: const TextStyle(fontWeight: FontWeight.w700),
          ));
          i = end + 2;
          continue;
        }
      }
      if (text[i] == '*') {
        final end = text.indexOf('*', i + 1);
        if (end >= 0 && end > i + 1 && !text.startsWith('**', end)) {
          spans.add(TextSpan(
            text: text.substring(i + 1, end),
            style: const TextStyle(color: Color(0xFFB4A8FF), fontStyle: FontStyle.italic),
          ));
          i = end + 1;
          continue;
        }
      }
      final nextStar = text.indexOf('*', i + 1);
      if (nextStar == -1) {
        spans.add(TextSpan(text: text.substring(i)));
        break;
      }
      spans.add(TextSpan(text: text.substring(i, nextStar)));
      i = nextStar;
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

// ── emotion phrases derived from character tags / personality ─────────────────
List<String> _emotionPhrases(Character char) {
  final tags = char.tags.map((t) => t.toLowerCase()).toSet();
  final pers = char.personality.toLowerCase();

  // build a pool from tag and personality signals — stays in-world, no AI tells
  final pool = <String>[];

  if (tags.contains('shy') || pers.contains('shy') || pers.contains('timid')) {
    pool.addAll(['fidgets quietly', 'glances away', 'takes a breath']);
  }
  if (tags.contains('flirty') || pers.contains('flirt') || pers.contains('seductive')) {
    pool.addAll(['smiles to herself', 'tilts her head', 'lets the silence stretch']);
  }
  if (tags.contains('cold') || tags.contains('stoic') || pers.contains('stoic') || pers.contains('cold')) {
    pool.addAll(['stares ahead', 'says nothing yet', 'waits']);
  }
  if (tags.contains('cheerful') || tags.contains('energetic') || pers.contains('cheerful') || pers.contains('energetic')) {
    pool.addAll(['practically bouncing', 'eyes light up', 'grins']);
  }
  if (tags.contains('serious') || pers.contains('serious') || pers.contains('stern')) {
    pool.addAll(['considers carefully', 'weighs the words', 'pauses']);
  }
  if (tags.contains('villain') || tags.contains('dark') || pers.contains('villain') || pers.contains('cruel')) {
    pool.addAll(['a slow smile', 'lets it linger', 'tilts her head slowly']);
  }
  if (tags.contains('caring') || tags.contains('nurturing') || pers.contains('caring') || pers.contains('warm')) {
    pool.addAll(['thinks it over', 'softens', 'nods slowly']);
  }
  if (tags.contains('tsundere') || pers.contains('tsundere')) {
    pool.addAll(['crosses her arms', 'looks away', 'huffs quietly']);
  }
  if (tags.contains('wise') || tags.contains('mentor') || pers.contains('wise') || pers.contains('mentor')) {
    pool.addAll(['lets the silence speak', 'chooses her words', 'pauses in thought']);
  }
  if (tags.contains('playful') || pers.contains('playful') || pers.contains('mischiev')) {
    pool.addAll(['a little smirk', 'half a laugh', 'eyes dancing']);
  }

  // generic fallback — always in-world
  if (pool.isEmpty) {
    pool.addAll(['thinking', 'a moment passes', 'takes a breath', 'pauses']);
  }

  return pool;
}

class _TypingIndicator extends StatefulWidget {
  final Character char;
  const _TypingIndicator({required this.char});
  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator> {
  late String _phrase;
  late final List<String> _pool;

  @override
  void initState() {
    super.initState();
    _pool = _emotionPhrases(widget.char);
    _pool.shuffle();
    _phrase = _pool.first;
  }

  @override
  Widget build(BuildContext context) {
    final acc = accentFor(widget.char.name);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          CharAvatar(name: widget.char.name, path: widget.char.avatar, size: 30, radius: 10),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: kBubbleChar,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(18),
                topRight: Radius.circular(18),
                bottomLeft: Radius.circular(5),
                bottomRight: Radius.circular(18),
              ),
              border: Border.all(color: kBorder, width: 0.8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _phrase,
                  style: TextStyle(
                    color: acc.first.withValues(alpha: 0.75),
                    fontSize: 13,
                    fontStyle: FontStyle.italic,
                    height: 1.3,
                  ),
                ),
                const SizedBox(width: 8),
                const _Dots(),
              ],
            ),
          ),
        ],
      ),
    );
  }
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
                width: 6, height: 6,
                decoration: BoxDecoration(
                  color: kMuted.withValues(alpha: 0.4 + 0.55 * (1 - (2 * t - 1).abs())),
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
          color: kDanger.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: kDanger.withValues(alpha: 0.35)),
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
                side: BorderSide(color: kDanger.withValues(alpha: 0.5)),
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
  final bool streaming;
  final VoidCallback onStop;

  const _InputBar({required this.controller, required this.onSend, required this.enabled, required this.streaming, required this.onStop});

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
                onTap: streaming ? onStop : (enabled ? onSend : null),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    gradient: streaming || enabled ? kGradient : null,
                    color: streaming || enabled ? null : kBorder,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(streaming ? Icons.stop_rounded : Icons.arrow_upward_rounded,
                      color: streaming || enabled ? Colors.white : kMuted, size: 22),
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
  final String storyStateKey;
  final CharacterProfileMemory profile;
  final VoidCallback onChanged;

  const _MemoryPanel({required this.charId, required this.storyStateKey, required this.facts, required this.profile, required this.onChanged});

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

  Future<void> _editFact(int i) async {
    final controller = TextEditingController(text: widget.facts[i]);
    final saved = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Edit memory'),
      content: TextField(controller: controller, autofocus: true, maxLines: 3),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save'))],
    ));
    if (saved == true) { StorageService.instance.editMemoryFact(widget.charId, i, controller.text); widget.onChanged(); }
    controller.dispose();
  }

  Future<void> _editProfile() async {
    final fields = <String, TextEditingController>{
      'personality': TextEditingController(text: widget.profile.personality),
      'motivations': TextEditingController(text: widget.profile.motivations),
      'speechStyle': TextEditingController(text: widget.profile.speechStyle),
      'background': TextEditingController(text: widget.profile.background),
      'boundaries': TextEditingController(text: widget.profile.boundaries),
    };
    try {
      final saved = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
        title: const Text('Edit character profile memory'),
        content: SizedBox(width: 420, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          for (final entry in fields.entries) Padding(padding: const EdgeInsets.only(bottom: 10), child: TextField(
            controller: entry.value, maxLines: 3, minLines: 1,
            decoration: InputDecoration(labelText: switch (entry.key) { 'speechStyle' => 'Speech style', 'motivations' => 'Motivations and goals', 'background' => 'Background canon', 'boundaries' => 'Boundaries', _ => 'Core personality' }),
          )),
        ]))),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')), FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save'))],
      ));
      if (saved == true) {
        StorageService.instance.saveCharacterProfile(widget.charId, CharacterProfileMemory(
          personality: fields['personality']!.text.trim(), motivations: fields['motivations']!.text.trim(),
          speechStyle: fields['speechStyle']!.text.trim(), background: fields['background']!.text.trim(),
          boundaries: fields['boundaries']!.text.trim(),
        ));
        widget.onChanged();
      }
    } finally { for (final c in fields.values) { c.dispose(); } }
  }

  Future<void> _editStoryState() async {
    final state = StorageService.instance.loadStoryState(widget.storyStateKey);
    final fields = <String, TextEditingController>{
      'scene': TextEditingController(text: state.currentScene),
      'character': TextEditingController(text: state.characterState),
      'relationship': TextEditingController(text: state.relationshipState),
      'user': TextEditingController(text: state.userState),
      'continuity': TextEditingController(text: state.continuityNotes),
      'events': TextEditingController(text: state.keyEvents.join('\n')),
      'threads': TextEditingController(text: state.openThreads.join('\n')),
    };
    try {
      final saved = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
        title: const Text('Edit story memory'),
        content: SizedBox(width: 460, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          for (final entry in fields.entries) Padding(padding: const EdgeInsets.only(bottom: 10), child: TextField(
            controller: entry.value, maxLines: entry.key == 'events' || entry.key == 'threads' || entry.key == 'continuity' ? 4 : 2,
            decoration: InputDecoration(labelText: switch (entry.key) { 'scene' => 'Current scene', 'character' => 'Character state', 'relationship' => 'Relationship', 'user' => 'User character state', 'continuity' => 'Continuity details', 'events' => 'Important events (one per line)', _ => 'Open threads (one per line)' }),
          )),
        ]))),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')), FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save'))],
      ));
      if (saved == true) {
        StorageService.instance.saveStoryState(widget.storyStateKey, StoryState(
          currentScene: fields['scene']!.text.trim(), characterState: fields['character']!.text.trim(),
          relationshipState: fields['relationship']!.text.trim(), userState: fields['user']!.text.trim(),
          continuityNotes: fields['continuity']!.text.trim(),
          keyEvents: fields['events']!.text.split('\n').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
          openThreads: fields['threads']!.text.split('\n').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
        ));
        widget.onChanged();
      }
    } finally { for (final c in fields.values) { c.dispose(); } }
  }

  @override
  Widget build(BuildContext context) => Container(
    width: (MediaQuery.of(context).size.width * 0.72).clamp(220.0, 300.0).toDouble(),
    decoration: BoxDecoration(
      color: kSurface.withValues(alpha: 0.97),
      border: const Border(left: BorderSide(color: kBorder, width: 0.5)),
      boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 20)],
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(12, 12, 12, 6),
          child: Text('MEMORY & STORY STATE', style: TextStyle(color: kMuted, fontSize: 11, letterSpacing: 0.8, fontWeight: FontWeight.w700)),
        ),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 8), child: Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: _editProfile, icon: const Icon(Icons.person_outline, size: 14), label: const Text('Character profile', style: TextStyle(fontSize: 10)))),
          const SizedBox(width: 5),
          Expanded(child: OutlinedButton.icon(onPressed: _editStoryState, icon: const Icon(Icons.edit_note, size: 14), label: const Text('Edit story', style: TextStyle(fontSize: 10)))),
        ])),
        Expanded(
          child: Column(
            children: [
              if (!widget.profile.isEmpty)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.fromLTRB(8, 4, 8, 6),
                  padding: const EdgeInsets.all(9),
                  decoration: BoxDecoration(color: kCard, borderRadius: BorderRadius.circular(7), border: Border.all(color: kBorder)),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('STABLE CHARACTER PROFILE', style: TextStyle(color: kPrimary, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
                    const SizedBox(height: 5),
                    for (final item in <String, String>{
                      'Personality': widget.profile.personality,
                      'Motivations': widget.profile.motivations,
                      'Speech style': widget.profile.speechStyle,
                      'Background': widget.profile.background,
                      'Boundaries': widget.profile.boundaries,
                    }.entries.where((e) => e.value.trim().isNotEmpty))
                      Padding(padding: const EdgeInsets.only(bottom: 3), child: Text('${item.key}: ${item.value}', style: const TextStyle(color: kTextSoft, fontSize: 10.5))),
                  ]),
                ),
              Builder(builder: (context) {
                final story = StorageService.instance.loadStoryState(widget.storyStateKey);
                if (story.isEmpty) return const SizedBox.shrink();
                final sections = <String, String>{
                  'CURRENT SCENE': story.currentScene,
                  'CHARACTER STATE': story.characterState,
                  'RELATIONSHIP': story.relationshipState,
                  'YOUR CHARACTER': story.userState,
                  'CONTINUITY': story.continuityNotes,
                  if (story.keyEvents.isNotEmpty) 'IMPORTANT EVENTS': story.keyEvents.map((e) => '• $e').join('\n'),
                  if (story.openThreads.isNotEmpty) 'OPEN THREADS': story.openThreads.map((e) => '• $e').join('\n'),
                }..removeWhere((key, value) => value.trim().isEmpty);
                return SizedBox(
                  height: 230,
                  child: SingleChildScrollView(
                    child: Container(
                      margin: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                      padding: const EdgeInsets.all(9),
                      decoration: BoxDecoration(color: kPrimary.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(7), border: Border.all(color: kPrimary.withValues(alpha: 0.25))),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('STORY CONTINUITY', style: TextStyle(color: kPrimary, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6)),
                        const SizedBox(height: 6),
                        ...sections.entries.map((entry) => Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(entry.key, style: const TextStyle(color: kMuted, fontSize: 9, fontWeight: FontWeight.w700)),
                            const SizedBox(height: 2),
                            Text(entry.value, style: const TextStyle(color: kTextSoft, fontSize: 11.5, height: 1.3)),
                          ]),
                        )),
                      ]),
                    ),
                  ),
                );
              }),
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
                        IconButton(padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 25, minHeight: 28),
                          onPressed: () => StorageService.instance.togglePinnedMemory(widget.charId, widget.facts[i]),
                          icon: Icon(StorageService.instance.loadPinnedMemory(widget.charId).contains(widget.facts[i]) ? Icons.push_pin : Icons.push_pin_outlined,
                            size: 14, color: StorageService.instance.loadPinnedMemory(widget.charId).contains(widget.facts[i]) ? kAmber : kMuted)),
                        IconButton(padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 25, minHeight: 28),
                          onPressed: () => _editFact(i), icon: const Icon(Icons.edit_outlined, size: 14, color: kMuted)),
                        IconButton(padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 25, minHeight: 28),
                          onPressed: () => _delete(i), icon: const Icon(Icons.close, size: 14, color: kMuted)),
                      ],
                    ),
                  ),
                ),
              ),
            ],
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
                  decoration: BoxDecoration(color: kPrimary.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(6)),
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
                              color: active ? kPrimary.withValues(alpha: 0.18) : kCard,
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
                            boxShadow: active ? [BoxShadow(color: kPrimary.withValues(alpha: 0.4), blurRadius: 8)] : null,
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
                  boxShadow: active ? [BoxShadow(color: kPrimary.withValues(alpha: 0.4), blurRadius: 6)] : null,
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
            color: active ? kPrimary.withValues(alpha: 0.12) : kCard,
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
                              color: kDanger.withValues(alpha: 0.15),
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

// ── Wallet Panel ──────────────────────────────────────────────────────────────

class _WalletPanel extends StatefulWidget {
  final SessionWallet wallet;
  final String charName;
  final void Function(WalletEntry) onManualEntry;
  const _WalletPanel({required this.wallet, required this.charName, required this.onManualEntry});
  @override
  State<_WalletPanel> createState() => _WalletPanelState();
}

class _WalletPanelState extends State<_WalletPanel> {
  final _amtCtrl   = TextEditingController();
  final _labelCtrl = TextEditingController();
  String _owner = 'user';
  bool   _earn  = true;

  @override
  void dispose() { _amtCtrl.dispose(); _labelCtrl.dispose(); super.dispose(); }

  void _submit() {
    final amt = int.tryParse(_amtCtrl.text.trim()) ?? 0;
    if (amt <= 0) return;
    widget.onManualEntry(WalletEntry(
      time:   DateTime.now(),
      owner:  _owner,
      amount: _earn ? amt : -amt,
      label:  _labelCtrl.text.trim(),
    ));
    _amtCtrl.clear();
    _labelCtrl.clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final w      = widget.wallet;
    final sym    = w.currencySymbol;
    final recent = w.ledger.reversed.take(20).toList();
    return Container(
      width: 260,
      decoration: BoxDecoration(
        color: kCard,
        border: Border(left: BorderSide(color: kBorder)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
            child: Text('Wallet', style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 15)),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(children: [
              Expanded(child: _BalanceTile(label: 'You',          balance: w.userBalance, sym: sym)),
              const SizedBox(width: 8),
              Expanded(child: _BalanceTile(label: widget.charName, balance: w.charBalance, sym: sym)),
            ]),
          ),
          const SizedBox(height: 10),
          const Divider(height: 1, color: kBorder),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
            child: Text('Manual', style: const TextStyle(color: kMuted, fontSize: 11)),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Column(children: [
              Row(children: [
                Expanded(
                  child: SegmentedButton<String>(
                    segments: [
                      ButtonSegment(value: 'user', label: Text('You',                                   style: const TextStyle(fontSize: 11))),
                      ButtonSegment(value: 'char', label: Text(widget.charName.split(' ').first, style: const TextStyle(fontSize: 11))),
                    ],
                    selected: {_owner},
                    onSelectionChanged: (s) => setState(() => _owner = s.first),
                    style: ButtonStyle(visualDensity: VisualDensity.compact, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                  ),
                ),
              ]),
              const SizedBox(height: 6),
              Row(children: [
                Expanded(
                  child: SegmentedButton<bool>(
                    segments: const [
                      ButtonSegment(value: true,  label: Text('Earn',  style: TextStyle(fontSize: 11))),
                      ButtonSegment(value: false, label: Text('Spend', style: TextStyle(fontSize: 11))),
                    ],
                    selected: {_earn},
                    onSelectionChanged: (s) => setState(() => _earn = s.first),
                    style: ButtonStyle(visualDensity: VisualDensity.compact, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                  ),
                ),
              ]),
              const SizedBox(height: 6),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _amtCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(hintText: 'Amount', isDense: true, prefixText: '$sym '),
                    style: const TextStyle(color: kText, fontSize: 13),
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: TextField(
                    controller: _labelCtrl,
                    decoration: const InputDecoration(hintText: 'Label', isDense: true),
                    style: const TextStyle(color: kText, fontSize: 13),
                  ),
                ),
                const SizedBox(width: 6),
                IconButton(
                  icon: const Icon(Icons.check_rounded, size: 18),
                  onPressed: _submit,
                  color: kPrimary,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ]),
            ]),
          ),
          const SizedBox(height: 8),
          const Divider(height: 1, color: kBorder),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 8, 14, 4),
            child: Text('Ledger', style: const TextStyle(color: kMuted, fontSize: 11)),
          ),
          Expanded(
            child: recent.isEmpty
                ? const Center(child: Text('No transactions yet', style: TextStyle(color: kMuted, fontSize: 12)))
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
                    itemCount: recent.length,
                    itemBuilder: (_, i) {
                      final e    = recent[i];
                      final plus = e.amount >= 0;
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(children: [
                          Icon(plus ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
                              size: 12, color: plus ? Colors.greenAccent : Colors.redAccent),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              '${e.owner == 'user' ? 'You' : widget.charName.split(' ').first}'
                              '${e.label.isNotEmpty ? ' · ${e.label}' : ''}',
                              style: const TextStyle(color: kText, fontSize: 11),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            '${plus ? '+' : ''}${e.amount} $sym',
                            style: TextStyle(
                              color: plus ? Colors.greenAccent : Colors.redAccent,
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ]),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _BalanceTile extends StatelessWidget {
  final String label;
  final int    balance;
  final String sym;
  const _BalanceTile({required this.label, required this.balance, required this.sym});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
    decoration: BoxDecoration(
      color: kSurface,
      borderRadius: BorderRadius.circular(10),
      border: Border.all(color: kBorder),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,         style: const TextStyle(color: kMuted, fontSize: 10)),
        const SizedBox(height: 2),
        Text('$sym $balance', style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 14)),
      ],
    ),
  );
}


class _RelationshipSheet extends StatefulWidget {
  final String charName;
  final RelationshipState initial;
  const _RelationshipSheet({required this.charName, required this.initial});
  @override
  State<_RelationshipSheet> createState() => _RelationshipSheetState();
}

class _RelationshipSheetState extends State<_RelationshipSheet> {
  late int familiarity, trust, affection, rivalry;
  late final TextEditingController notes, events;
  @override
  void initState() {
    super.initState(); final r = widget.initial;
    familiarity = r.familiarity; trust = r.trust; affection = r.affection; rivalry = r.rivalry;
    notes = TextEditingController(text: r.notes); events = TextEditingController(text: r.sharedEvents.join('\n'));
  }
  @override
  void dispose() { notes.dispose(); events.dispose(); super.dispose(); }
  Widget _score(String label, int value, ValueChanged<double> update, Color color) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Row(children: [Expanded(child: Text(label, style: const TextStyle(color: kText))), Text('$value / 100', style: TextStyle(color: color, fontWeight: FontWeight.w700))]),
    Slider(value: value.toDouble(), min: 0, max: 100, divisions: 20, activeColor: color, onChanged: update),
  ]);
  @override
  Widget build(BuildContext context) => DraggableScrollableSheet(initialChildSize: .8, maxChildSize: .95, builder: (_, scroll) => Container(
    decoration: const BoxDecoration(color: kSurface, borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    child: ListView(controller: scroll, padding: const EdgeInsets.all(20), children: [
      Text('${widget.charName} · Relationship', style: const TextStyle(color: kText, fontSize: 20, fontWeight: FontWeight.w800)),
      const Text('Scores are explicit and editable; they do not change randomly.', style: TextStyle(color: kMuted, fontSize: 12)),
      const SizedBox(height: 14),
      _score('Familiarity', familiarity, (v) => setState(() => familiarity = v.round()), kCyan),
      _score('Trust', trust, (v) => setState(() => trust = v.round()), kGreen),
      _score('Affection', affection, (v) => setState(() => affection = v.round()), kPrimary2),
      _score('Rivalry', rivalry, (v) => setState(() => rivalry = v.round()), kAmber),
      const SizedBox(height: 8), const Text('Relationship notes', style: TextStyle(color: kText, fontWeight: FontWeight.w700)),
      const SizedBox(height: 6), TextField(controller: notes, maxLines: 3, decoration: const InputDecoration(hintText: 'Boundaries, current dynamic, unresolved tension…')),
      const SizedBox(height: 14), const Text('Shared events (one per line)', style: TextStyle(color: kText, fontWeight: FontWeight.w700)),
      const SizedBox(height: 6), TextField(controller: events, maxLines: 4, decoration: const InputDecoration(hintText: 'The promise made at the tower…')),
      const SizedBox(height: 16), FilledButton(onPressed: () => Navigator.pop(context, RelationshipState(
        familiarity: familiarity, trust: trust, affection: affection, rivalry: rivalry, notes: notes.text.trim(),
        sharedEvents: events.text.split('\n').map((e) => e.trim()).where((e) => e.isNotEmpty).take(30).toList(),
      )), child: const Text('Save relationship')),
    ]),
  ));
}
