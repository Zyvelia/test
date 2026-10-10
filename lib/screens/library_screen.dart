// library_screen.dart — character library

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import '../models/models.dart';
import '../providers/app_provider.dart';
import '../services/ollama_service.dart';
import '../services/storage_service.dart';
import '../theme.dart';

class LibraryScreen extends StatefulWidget {
  final void Function(Character) onOpenChar;
  const LibraryScreen({super.key, required this.onOpenChar});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final _search = TextEditingController();
  String _catFilter = 'All';
  String _sortMode = 'A–Z';
  static const _cats = [
    'All', 'Original', 'Anime', 'Fantasy', 'Games', 'Sci-Fi',
    'Historical', 'Roleplay', 'Horror', 'Slice of Life', 'Other',
  ];

  List<Character> _filtered(List<Character> all) {
    final q = _search.text.toLowerCase();
    return all.where((c) {
      if (_catFilter != 'All' && c.category != _catFilter) return false;
      if (q.isEmpty) return true;
      final hay = '${c.name} ${c.category} ${c.tags.join(' ')} ${c.personality}'.toLowerCase();
      return hay.contains(q);
    }).toList()
      ..sort((a, b) {
        switch (_sortMode) {
          case 'Newest':
            return all.indexOf(b).compareTo(all.indexOf(a));
          case 'Recently chatted':
            final ah = StorageService.instance.loadChat(a.id);
            final bh = StorageService.instance.loadChat(b.id);
            final at = ah.isEmpty ? DateTime.fromMillisecondsSinceEpoch(0) : ah.last.timestamp;
            final bt = bh.isEmpty ? DateTime.fromMillisecondsSinceEpoch(0) : bh.last.timestamp;
            return bt.compareTo(at);
          default:
            return a.name.toLowerCase().compareTo(b.name.toLowerCase());
        }
      });
  }

  void _openCreate(BuildContext context) async {
    final ap = context.read<AppProvider>();
    final result = await showModalBottomSheet<Character>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => CharacterSheet(settings: ap.settings),
    );
    if (result != null) ap.saveCharacter(result);
  }

  void _openEdit(BuildContext context, Character c) async {
    final ap = context.read<AppProvider>();
    final result = await showModalBottomSheet<Character>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => CharacterSheet(character: c, settings: ap.settings),
    );
    if (result != null) ap.saveCharacter(result);
  }

  void _confirmDelete(BuildContext context, Character c) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete character'),
        content: Text('Delete ${c.name} and their chat history?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              context.read<AppProvider>().deleteCharacter(c.id);
              Navigator.pop(context);
            },
            child: const Text('Delete', style: TextStyle(color: kDanger)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ap = context.watch<AppProvider>();
    final chars = _filtered(ap.characters);

    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        title: const GradientText('Characters', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 26)),
        centerTitle: false,
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Sort characters',
            icon: const Icon(Icons.sort_rounded, color: kMuted),
            initialValue: _sortMode,
            onSelected: (v) => setState(() => _sortMode = v),
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'A–Z', child: Text('A–Z')),
              PopupMenuItem(value: 'Recently chatted', child: Text('Recently chatted')),
              PopupMenuItem(value: 'Newest', child: Text('Newest')),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              controller: _search,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                hintText: 'Search characters…',
                prefixIcon: Icon(Icons.search, color: kMuted),
              ),
              style: const TextStyle(color: kText),
            ),
          ),
          SizedBox(
            height: 40,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              itemCount: _cats.length,
              separatorBuilder: (_, __) => const SizedBox(width: 6),
              itemBuilder: (_, i) {
                final cat = _cats[i];
                final active = cat == _catFilter;
                final col = cat == 'All' ? kPrimary : categoryColor(cat);
                return FilterChip(
                  label: Text(cat, style: TextStyle(color: active ? Colors.white : col, fontSize: 12.5, fontWeight: FontWeight.w600)),
                  selected: active,
                  onSelected: (_) => setState(() => _catFilter = cat),
                  backgroundColor: col.withValues(alpha: 0.10),
                  selectedColor: col.withValues(alpha: 0.55),
                  side: BorderSide(color: col.withValues(alpha: active ? 0.9 : 0.35), width: 1),
                  showCheckmark: false,
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                );
              },
            ),
          ),
                    Expanded(
            child: chars.isEmpty
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.auto_awesome, color: kPrimary, size: 44),
                        const SizedBox(height: 12),
                        Text(
                          ap.characters.isEmpty ? 'No characters yet — tap New to create one.' : 'No matches.',
                          style: const TextStyle(color: kMuted),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 90),
                    itemCount: chars.length,
                    itemBuilder: (_, i) => _CharCard(
                      char: chars[i],
                      onChat: () {
                        context.read<AppProvider>().setActiveChar(chars[i]);
                        widget.onOpenChar(chars[i]);
                      },
                      onEdit: () => _openEdit(context, chars[i]),
                      onDelete: () => _confirmDelete(context, chars[i]),
                    ),
                  ),
          ),
        ],
      ),
      floatingActionButton: Container(
        decoration: BoxDecoration(
          gradient: kGradient,
          borderRadius: BorderRadius.circular(18),
          boxShadow: [BoxShadow(color: kPrimary.withValues(alpha: 0.4), blurRadius: 16, offset: const Offset(0, 6))],
        ),
        child: FloatingActionButton.extended(
          backgroundColor: Colors.transparent,
          elevation: 0,
          highlightElevation: 0,
          foregroundColor: Colors.white,
          onPressed: () => _openCreate(context),
          icon: const Icon(Icons.add),
          label: const Text('New', style: TextStyle(fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }
}

// ── CharCard ──────────────────────────────────────────────────────────────────

class _CharCard extends StatelessWidget {
  final Character char;
  final VoidCallback onChat, onEdit, onDelete;
  const _CharCard({required this.char, required this.onChat, required this.onEdit, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final acc = accentFor(char.name);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [acc.first.withValues(alpha: 0.16), kCard, kCard],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: acc.first.withValues(alpha: 0.35), width: 1),
        boxShadow: [BoxShadow(color: acc.first.withValues(alpha: 0.10), blurRadius: 14, offset: const Offset(0, 4))],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onChat,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                CharAvatar(name: char.name, path: char.avatar, size: 58, radius: 18),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(char.name,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 16)),
                          ),
                          if (char.nsfw) ...[
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: kDanger.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: const Text('18+',
                                  style: TextStyle(color: kDanger, fontSize: 10, fontWeight: FontWeight.w700)),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 3),
                      Text(
                        char.personality.isNotEmpty
                            ? char.personality.replaceAll('\n', ' ')
                            : char.category,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: kMuted, fontSize: 12.5, height: 1.35),
                      ),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          _pill(char.category, categoryColor(char.category)),
                          for (final t in char.tags.take(2)) _pill('#$t', acc.last),
                        ],
                      ),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  icon: const Icon(Icons.more_vert, color: kMuted, size: 20),
                  color: kCard,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  onSelected: (v) => v == 'edit' ? onEdit() : onDelete(),
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 'edit', child: Text('Edit', style: TextStyle(color: kText))),
                    PopupMenuItem(value: 'delete', child: Text('Delete', style: TextStyle(color: kDanger))),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _pill(String t, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: c.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: c.withValues(alpha: 0.35), width: 0.7),
        ),
        child: Text(t, style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w500)),
      );
}

// ── CharacterSheet ─────────────────────────────────────────────────────────────

class CharacterSheet extends StatefulWidget {
  final Character? character;
  final AppSettings settings;
  const CharacterSheet({super.key, this.character, required this.settings});

  @override
  State<CharacterSheet> createState() => _CharacterSheetState();
}

class _CharacterSheetState extends State<CharacterSheet> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  late final TextEditingController _name, _avatar, _personality, _scenario, _greeting, _tags, _nsfwDesc, _currencyName, _currencySymbol, _modelOverride;
  late final TextEditingController _concept;
  String _category = 'Original';
  String _visibility = 'Private';
  bool _nsfw = false;
  bool _wizardExpanded = false;
  final Map<String, bool> _generating = {};

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    final c = widget.character;
    _concept     = TextEditingController();
    _name        = TextEditingController(text: c?.name ?? '');
    _avatar      = TextEditingController(text: c?.avatar ?? '');
    _personality = TextEditingController(text: c?.personality ?? '');
    _scenario    = TextEditingController(text: c?.scenario ?? '');
    _greeting    = TextEditingController(text: c?.greeting ?? '');
    _tags        = TextEditingController(text: c?.tags.join(', ') ?? '');
    _nsfwDesc       = TextEditingController(text: c?.nsfwDescription ?? '');
    _currencyName   = TextEditingController(text: c?.currencyName ?? '');
    _currencySymbol = TextEditingController(text: c?.currencySymbol ?? '');
    _modelOverride = TextEditingController(text: c?.modelOverride ?? '');
    _category    = c?.category ?? 'Original';
    _visibility  = c?.visibility ?? 'Private';
    _nsfw        = c?.nsfw ?? false;
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final c in [_concept, _name, _avatar, _personality, _scenario, _greeting, _tags, _nsfwDesc, _currencyName, _currencySymbol, _modelOverride]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _generate(String key, TextEditingController target, String prompt) async {
    setState(() => _generating[key] = true);
    try {
      final text = await OllamaService.instance.generate(
        baseUrl: widget.settings.ollamaUrl,
        model: widget.settings.model,
        prompt: prompt,
      );
      // Guard mounted — sheet may have been dismissed during the 180s window
      if (mounted) setState(() => target.text = text);
    } catch (e) {
      if (mounted) {
        // Dialog works inside a bottom sheet; ScaffoldMessenger resolves to the
        // sheet's scaffold and the snackbar fires into void.
        showDialog(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Generation failed'),
            content: Text(OllamaService.friendlyError(e)),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _generating[key] = false);
    }
  }

  String get _nameStr => _name.text.trim().isEmpty ? 'the character' : _name.text.trim();
  List<String> get _tagsList => _tags.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();

  void _genPersonality() => _generate(
    'personality', _personality,
    'Write a detailed personality profile for a character named $_nameStr in the $_category genre.'
    '${_tagsList.isNotEmpty ? ' Tags: ${_tagsList.join(', ')}.' : ''}'
    ' Include speech style, mannerisms, emotional tendencies, and quirks. 2-3 paragraphs. Return only the description.',
  );

  void _genScenario() => _generate(
    'scenario', _scenario,
    'Write a vivid scenario and setting for $_nameStr, a $_category character.'
    '${_personality.text.isNotEmpty ? ' Their personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 400))}.' : ''}'
    ' 1-2 paragraphs. Return only the scenario.',
  );

  void _genGreeting() => _generate(
    'greeting', _greeting,
    'Write the opening message $_nameStr sends to start a conversation.'
    '${_personality.text.isNotEmpty ? ' Personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 300))}.' : ''}'
    '${_scenario.text.isNotEmpty ? ' Scenario: ${_scenario.text.substring(0, _scenario.text.length.clamp(0, 200))}.' : ''}'
    ' Use CAI-style: action in *asterisks*, dialogue plain. 1-4 sentences. Return only the message.',
  );

  void _genNsfw() => _generate(
    'nsfw', _nsfwDesc,
    'Write explicit adult context for $_nameStr, a $_category character.'
    '${_personality.text.isNotEmpty ? ' Personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 400))}.' : ''}'
    ' Include sexual personality, preferences, and behavior in adult scenarios. Be explicit. Return only the description.',
  );

  // AI Wizard — generates name + all fields from a freeform concept string
  Future<void> _wizardGenerate() async {
    final concept = _concept.text.trim();
    if (concept.isEmpty) {
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Describe your idea'),
          content: const Text('Type a short concept in the box above — e.g. "a cold detective who distrusts magic" — then tap Generate.'),
          actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
        ),
      );
      return;
    }
    setState(() => _generating['wizard'] = true);
    try {
      // Step 1: generate a structured JSON character brief from the concept
      final briefPrompt =
          'You are a character creation assistant. Given the concept below, return a JSON object with these exact keys:\n'
          '"name" (string), "category" (one of: Original,Anime,Fantasy,Games,Sci-Fi,Historical,Roleplay,Horror,Slice of Life,Other),\n'
          '"tags" (array of 3-5 short trait strings), "personality" (2-3 paragraphs),\n'
          '"scenario" (1-2 paragraphs setting the scene), "greeting" (1-4 sentence opening message in CAI style: *action* and plain dialogue).\n'
          'Return ONLY valid JSON, no markdown fences, no commentary.\n\n'
          'Concept: $concept\n'
          'Genre preference: $_category\n'
          '${_nsfw ? "This character is for adult/explicit content." : ""}';

      final raw = await OllamaService.instance.generate(
        baseUrl: widget.settings.ollamaUrl,
        model: widget.settings.model,
        prompt: briefPrompt,
      );

      final j = OllamaService.parseStructuredJson(raw);
      if (j == null) {
        if (mounted) {
          showDialog(
            context: context,
            builder: (_) => AlertDialog(
              title: const Text('Could not parse that'),
              content: SingleChildScrollView(child: Text(raw.trim())),
              actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
            ),
          );
        }
      } else if (mounted) {
        setState(() {
          if ((j['name'] as String?)?.isNotEmpty == true) _name.text = j['name'] as String;
          final cat = j['category'] as String?;
          if (cat != null && ['Original','Anime','Fantasy','Games','Sci-Fi','Historical','Roleplay','Horror','Slice of Life','Other'].contains(cat)) {
            _category = cat;
          }
          final tags = j['tags'];
          if (tags is List) _tags.text = tags.map((t) => t.toString()).join(', ');
          if ((j['personality'] as String?)?.isNotEmpty == true) _personality.text = j['personality'] as String;
          if ((j['scenario'] as String?)?.isNotEmpty == true) _scenario.text = j['scenario'] as String;
          if ((j['greeting'] as String?)?.isNotEmpty == true) _greeting.text = j['greeting'] as String;
          _wizardExpanded = false; // collapse wizard after success
        });
      }
    } catch (e) {
      if (mounted) {
        showDialog(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Generation failed'),
            content: Text(OllamaService.friendlyError(e)),
            actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _generating['wizard'] = false);
    }
  }

  // Improve an existing field — rewrites in place rather than replacing
  Future<void> _improve(String key, TextEditingController ctrl, String fieldName) async {
    if (ctrl.text.trim().isEmpty) return;
    setState(() => _generating['${key}_improve'] = true);
    try {
      final text = await OllamaService.instance.generate(
        baseUrl: widget.settings.ollamaUrl,
        model: widget.settings.model,
        prompt: 'Improve the following $fieldName for a character named $_nameStr in the $_category genre. '
                'Make it more vivid, specific, and character-driven. Keep the same core ideas. '
                'Return only the improved text, no commentary.\n\n${ctrl.text.trim()}',
      );
      if (mounted) setState(() => ctrl.text = text);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    } finally {
      if (mounted) setState(() => _generating['${key}_improve'] = false);
    }
  }

  void _autofillAll() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter a name first.')));
      return;
    }
    await _generate(
      'personality', _personality,
      'Write a detailed personality profile for $_nameStr in the $_category genre. 2-3 paragraphs. Return only the description.',
    );
    _genScenario();
    _genGreeting();
  }

  Character _buildCharacter() {
    final c = widget.character;
    return Character(
      id: c?.id ?? const Uuid().v4(),
      name: _name.text.trim().isEmpty ? 'Unnamed' : _name.text.trim(),
      category: _category,
      avatar: _avatar.text.trim(),
      personality: _personality.text.trim(),
      scenario: _scenario.text.trim(),
      greeting: _greeting.text.trim(),
      tags: _tagsList,
      visibility: _visibility,
      nsfw: _nsfw,
      nsfwDescription: _nsfwDesc.text.trim(),
      currencyName:   _currencyName.text.trim(),
      currencySymbol: _currencySymbol.text.trim(),
      modelOverride: _modelOverride.text.trim(),
    );
  }

  Widget _genBtn(String key, VoidCallback fn, {String tooltip = 'Generate with AI'}) => _generating[key] == true
      ? const Padding(
          padding: EdgeInsets.symmetric(horizontal: 8),
          child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: kPrimary)),
        )
      : TextButton.icon(
          icon: const Icon(Icons.auto_awesome, size: 14),
          label: const Text('Generate', style: TextStyle(fontSize: 12)),
          style: TextButton.styleFrom(foregroundColor: kPrimary, padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
          onPressed: fn,
        );

  Widget _improveBtn(String key, TextEditingController ctrl, String fieldName) {
    final improveKey = '${key}_improve';
    if (ctrl.text.trim().isEmpty) return const SizedBox.shrink();
    return _generating[improveKey] == true
        ? const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: kCyan)),
          )
        : TextButton.icon(
            icon: const Icon(Icons.edit_note, size: 14),
            label: const Text('Improve', style: TextStyle(fontSize: 12)),
            style: TextButton.styleFrom(foregroundColor: kCyan, padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
            onPressed: () => _improve(key, ctrl, fieldName),
          );
  }

  Widget _field(String label, TextEditingController ctrl, String key, VoidCallback genFn, {int maxLines = 4, String hint = '', String fieldName = ''}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label, style: const TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
            const Spacer(),
            _improveBtn(key, ctrl, fieldName.isEmpty ? label.toLowerCase() : fieldName),
            _genBtn(key, genFn),
          ],
        ),
        const SizedBox(height: 4),
        TextField(
          controller: ctrl,
          maxLines: maxLines,
          scrollPadding: const EdgeInsets.only(bottom: 120),
          decoration: InputDecoration(hintText: hint),
          style: const TextStyle(color: kText, fontSize: 13),
          onChanged: (_) => setState(() {}), // refresh improve btn visibility
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.character != null;
    final keyboardH = MediaQuery.of(context).viewInsets.bottom;
    return DraggableScrollableSheet(
      initialChildSize: 0.92,
      minChildSize: 0.5,
      maxChildSize: 0.97,
      expand: false,
      builder: (_, __) => GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        behavior: HitTestBehavior.opaque,
        child: Padding(
        padding: EdgeInsets.only(bottom: keyboardH),
        child: Container(
          decoration: const BoxDecoration(
            color: kSurface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(width: 36, height: 4, decoration: BoxDecoration(color: kBorder, borderRadius: BorderRadius.circular(2))),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 8, 0),
                child: Row(
                  children: [
                    Text(isEdit ? 'Edit Character' : 'New Character',
                        style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 17)),
                    const Spacer(),
                    TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                    const SizedBox(width: 4),
                    ElevatedButton(
                      onPressed: () => Navigator.pop(context, _buildCharacter()),
                      child: const Text('Save'),
                    ),
                  ],
                ),
              ),
              TabBar(
                controller: _tabs,
                tabs: const [Tab(text: 'Core'), Tab(text: 'Advanced / 18+')],
                labelColor: kPrimary,
                unselectedLabelColor: kMuted,
                indicatorColor: kPrimary,
                dividerColor: kBorder,
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabs,
                  children: [
                    // Core tab — own scroll controller, keyboard-aware
                    ListView(
                      padding: EdgeInsets.fromLTRB(20, 16, 20, keyboardH > 0 ? 16 : 32),
                      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                      children: [
                        TextField(
                          controller: _name,
                          scrollPadding: const EdgeInsets.only(bottom: 120),
                          decoration: const InputDecoration(labelText: 'Name *'),
                          style: const TextStyle(color: kText),
                        ),
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            Expanded(child: _dropdownRow('Category', _category,
                              ['Original','Anime','Fantasy','Games','Sci-Fi','Historical','Roleplay','Horror','Slice of Life','Other'],
                              (v) => setState(() => _category = v))),
                          ],
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          controller: _avatar,
                          scrollPadding: const EdgeInsets.only(bottom: 120),
                          decoration: const InputDecoration(labelText: 'Avatar path (optional)'),
                          style: const TextStyle(color: kText, fontSize: 13),
                        ),
                        const SizedBox(height: 14),
                        // ── AI Wizard ───────────────────────────────────────
                        GestureDetector(
                          onTap: () => setState(() => _wizardExpanded = !_wizardExpanded),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                            decoration: BoxDecoration(
                              gradient: LinearGradient(colors: [kPrimary.withValues(alpha: 0.18), kCyan.withValues(alpha: 0.10)]),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: kPrimary.withValues(alpha: 0.4)),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.auto_awesome, size: 16, color: kPrimary),
                                const SizedBox(width: 8),
                                const Expanded(child: Text('AI Character Wizard', style: TextStyle(color: kPrimary, fontWeight: FontWeight.w600, fontSize: 13))),
                                Icon(_wizardExpanded ? Icons.expand_less : Icons.expand_more, color: kPrimary, size: 18),
                              ],
                            ),
                          ),
                        ),
                        if (_wizardExpanded) ...[
                          const SizedBox(height: 10),
                          TextField(
                            controller: _concept,
                            maxLines: 3,
                            scrollPadding: const EdgeInsets.only(bottom: 120),
                            decoration: const InputDecoration(
                              hintText: 'Describe your idea… e.g. "a cold detective who distrusts magic and hides a dark past"',
                              border: OutlineInputBorder(),
                            ),
                            style: const TextStyle(color: kText, fontSize: 13),
                          ),
                          const SizedBox(height: 8),
                          SizedBox(
                            width: double.infinity,
                            child: ElevatedButton.icon(
                              icon: _generating['wizard'] == true
                                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                                  : const Icon(Icons.auto_awesome, size: 16),
                              label: Text(_generating['wizard'] == true ? 'Generating…' : 'Generate full character'),
                              onPressed: _generating['wizard'] == true ? null : _wizardGenerate,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: kPrimary,
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(vertical: 12),
                              ),
                            ),
                          ),
                          const SizedBox(height: 4),
                          const Text('Fills name, personality, scenario, greeting and tags all at once.', style: TextStyle(color: kMuted, fontSize: 11)),
                        ],
                        const SizedBox(height: 12),
                        // ── legacy per-field buttons ─────────────────────────
                        _field('Personality *', _personality, 'personality', _genPersonality, maxLines: 6,
                          hint: 'Personality, speech style, mannerisms, core traits…', fieldName: 'personality'),
                        _field('Scenario', _scenario, 'scenario', _genScenario, maxLines: 4,
                          hint: 'Setting, world, situation context…', fieldName: 'scenario'),
                        _field('Greeting', _greeting, 'greeting', _genGreeting, maxLines: 3,
                          hint: 'First message the character sends…', fieldName: 'greeting'),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Tags', style: TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                            const SizedBox(height: 4),
                            TextField(
                              controller: _tags,
                              scrollPadding: const EdgeInsets.only(bottom: 120),
                              decoration: const InputDecoration(hintText: 'e.g. tsundere, warrior, mentor (comma-separated)'),
                              style: const TextStyle(color: kText, fontSize: 13),
                            ),
                            const SizedBox(height: 32),
                          ],
                        ),
                      ],
                    ),
                    // Advanced tab — own scroll controller
                    ListView(
                      padding: EdgeInsets.fromLTRB(20, 16, 20, keyboardH > 0 ? 16 : 32),
                      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                      children: [
                        _dropdownRow('Visibility', _visibility, ['Private','Public'],
                          (v) => setState(() => _visibility = v)),
                        const SizedBox(height: 20),
                        const Text('Currency (leave blank — AI picks from the world)',
                            style: TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                        const SizedBox(height: 8),
                        Row(children: [
                          Expanded(
                            flex: 3,
                            child: TextField(
                              controller: _currencyName,
                              scrollPadding: const EdgeInsets.only(bottom: 120),
                              decoration: const InputDecoration(hintText: 'Name — e.g. gold, credits', isDense: true),
                              style: const TextStyle(color: kText, fontSize: 13),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            flex: 1,
                            child: TextField(
                              controller: _currencySymbol,
                              scrollPadding: const EdgeInsets.only(bottom: 120),
                              decoration: const InputDecoration(hintText: 'Symbol', isDense: true),
                              style: const TextStyle(color: kText, fontSize: 13),
                            ),
                          ),
                        ]),
                        const SizedBox(height: 20),
                        const Text('Model override (optional)', style: TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _modelOverride,
                          scrollPadding: const EdgeInsets.only(bottom: 120),
                          decoration: InputDecoration(
                            hintText: 'Default: ${widget.settings.model}',
                            helperText: 'Enter an installed Ollama model name. Leave blank to use Settings.',
                            helperMaxLines: 2,
                            isDense: true,
                          ),
                          style: const TextStyle(color: kText, fontSize: 13),
                        ),
                        const SizedBox(height: 20),
                        SwitchListTile(
                          title: const Text('Enable 18+ / NSFW', style: TextStyle(color: kText)),
                          subtitle: const Text('Explicit content enabled for this character', style: TextStyle(color: kMuted, fontSize: 12)),
                          value: _nsfw,
                          onChanged: (v) => setState(() => _nsfw = v),
                          activeColor: kPrimary,
                          contentPadding: EdgeInsets.zero,
                        ),
                        const SizedBox(height: 12),
                        if (_nsfw)
                          _field('NSFW context', _nsfwDesc, 'nsfw', _genNsfw, maxLines: 6,
                            hint: 'Explicit personality, kinks, adult scenario details…'),
                        const SizedBox(height: 32),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        ),
      ),
    );
  }

  Widget _dropdownRow(String label, String value, List<String> items, void Function(String) onChanged) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
        const SizedBox(height: 4),
        DropdownButtonFormField<String>(
          value: value,
          items: items.map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(color: kText)))).toList(),
          onChanged: (v) { if (v != null) onChanged(v); },
          decoration: const InputDecoration(),
          dropdownColor: kCard,
          style: const TextStyle(color: kText),
        ),
      ],
    );
  }
}
