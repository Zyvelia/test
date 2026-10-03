// library_screen.dart — character library

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import '../models/models.dart';
import '../providers/app_provider.dart';
import '../services/ollama_service.dart';
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
    }).toList();
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
                  backgroundColor: col.withOpacity(0.10),
                  selectedColor: col.withOpacity(0.55),
                  side: BorderSide(color: col.withOpacity(active ? 0.9 : 0.35), width: 1),
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
          boxShadow: [BoxShadow(color: kPrimary.withOpacity(0.4), blurRadius: 16, offset: const Offset(0, 6))],
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
          colors: [acc.first.withOpacity(0.16), kCard, kCard],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: acc.first.withOpacity(0.35), width: 1),
        boxShadow: [BoxShadow(color: acc.first.withOpacity(0.10), blurRadius: 14, offset: const Offset(0, 4))],
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
                                color: kDanger.withOpacity(0.15),
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
          color: c.withOpacity(0.16),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: c.withOpacity(0.35), width: 0.7),
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
  late final TextEditingController _name, _avatar, _personality, _scenario, _greeting, _examples, _tags, _nsfwDesc;
  String _category = 'Original';
  String _visibility = 'Private';
  bool _nsfw = false;
  final Map<String, bool> _generating = {};

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    final c = widget.character;
    _name        = TextEditingController(text: c?.name ?? '');
    _avatar      = TextEditingController(text: c?.avatar ?? '');
    _personality = TextEditingController(text: c?.personality ?? '');
    _scenario    = TextEditingController(text: c?.scenario ?? '');
    _greeting    = TextEditingController(text: c?.greeting ?? '');
    _examples    = TextEditingController(text: c?.examples ?? '');
    _tags        = TextEditingController(text: c?.tags.join(', ') ?? '');
    _nsfwDesc    = TextEditingController(text: c?.nsfwDescription ?? '');
    _category    = c?.category ?? 'Original';
    _visibility  = c?.visibility ?? 'Private';
    _nsfw        = c?.nsfw ?? false;
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final c in [_name, _avatar, _personality, _scenario, _greeting, _examples, _tags, _nsfwDesc]) {
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
      target.text = text;
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Generation failed: $e')),
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

  void _genExamples() => _generate(
    'examples', _examples,
    'Write 5 example dialogue exchanges between $_nameStr and ${widget.settings.userName}.'
    '${_personality.text.isNotEmpty ? ' Personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 400))}.' : ''}'
    ' Format:\n${widget.settings.userName}: ...\n$_nameStr: ...\n\n'
    'Character replies use *asterisks* for actions. Return only the formatted exchanges.',
  );

  void _genNsfw() => _generate(
    'nsfw', _nsfwDesc,
    'Write explicit adult context for $_nameStr, a $_category character.'
    '${_personality.text.isNotEmpty ? ' Personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 400))}.' : ''}'
    ' Include sexual personality, preferences, and behavior in adult scenarios. Be explicit. Return only the description.',
  );

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
    _genExamples();
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
      examples: _examples.text.trim(),
      tags: _tagsList,
      visibility: _visibility,
      nsfw: _nsfw,
      nsfwDescription: _nsfwDesc.text.trim(),
    );
  }

  Widget _genBtn(String key, VoidCallback fn) => IconButton(
    icon: _generating[key] == true
        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: kPrimary))
        : const Icon(Icons.auto_awesome, size: 18),
    onPressed: _generating[key] == true ? null : fn,
    color: kPrimary,
    tooltip: 'Generate with AI',
  );

  Widget _field(String label, TextEditingController ctrl, String key, VoidCallback genFn, {int maxLines = 4, String hint = ''}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label, style: const TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
            const Spacer(),
            _genBtn(key, genFn),
          ],
        ),
        const SizedBox(height: 4),
        TextField(
          controller: ctrl,
          maxLines: maxLines,
          decoration: InputDecoration(hintText: hint),
          style: const TextStyle(color: kText, fontSize: 13),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.character != null;
    return DraggableScrollableSheet(
      initialChildSize: 0.92,
      minChildSize: 0.5,
      maxChildSize: 0.97,
      expand: false,
      builder: (_, scrollController) => Container(
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
                  // Core tab
                  ListView(
                    controller: scrollController,
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
                    children: [
                      TextField(
                        controller: _name,
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
                        decoration: const InputDecoration(labelText: 'Avatar path (optional)'),
                        style: const TextStyle(color: kText, fontSize: 13),
                      ),
                      const SizedBox(height: 14),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.auto_awesome, size: 16),
                        label: const Text('Auto-fill all fields'),
                        onPressed: _autofillAll,
                      ),
                      const SizedBox(height: 20),
                      _field('Personality *', _personality, 'personality', _genPersonality, maxLines: 6,
                        hint: 'Personality, speech style, mannerisms, core traits…'),
                      _field('Scenario', _scenario, 'scenario', _genScenario, maxLines: 4,
                        hint: 'Setting, world, situation context…'),
                      _field('Greeting', _greeting, 'greeting', _genGreeting, maxLines: 3,
                        hint: 'First message the character sends…'),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Tags', style: TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                          const SizedBox(height: 4),
                          TextField(
                            controller: _tags,
                            decoration: const InputDecoration(hintText: 'e.g. tsundere, warrior, mentor (comma-separated)'),
                            style: const TextStyle(color: kText, fontSize: 13),
                          ),
                        ],
                      ),
                    ],
                  ),
                  // Advanced tab
                  ListView(
                    controller: scrollController,
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
                    children: [
                      _field('Example exchanges', _examples, 'examples', _genExamples, maxLines: 8,
                        hint: 'Example dialogue showing the character\'s voice…'),
                      _dropdownRow('Visibility', _visibility, ['Private','Public'],
                        (v) => setState(() => _visibility = v)),
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
                    ],
                  ),
                ],
              ),
            ),
          ],
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
