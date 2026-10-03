// personas_screen.dart — persona management

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import '../models/models.dart';
import '../providers/app_provider.dart';
import '../services/ollama_service.dart';
import '../theme.dart';

class PersonasScreen extends StatelessWidget {
  const PersonasScreen({super.key});

  void _openCreate(BuildContext context) async {
    final ap = context.read<AppProvider>();
    final result = await showModalBottomSheet<Persona>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => PersonaSheet(settings: ap.settings),
    );
    if (result != null) ap.savePersona(result);
  }

  void _openEdit(BuildContext context, Persona p) async {
    final ap = context.read<AppProvider>();
    final result = await showModalBottomSheet<Persona>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => PersonaSheet(persona: p, settings: ap.settings),
    );
    if (result != null) ap.savePersona(result);
  }

  void _confirmDelete(BuildContext context, Persona p) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete persona'),
        content: Text('Delete "${p.name}"?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              context.read<AppProvider>().deletePersona(p.id);
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

    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        title: const GradientText('Personas', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 26)),
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: kPrimary),
            onPressed: () => _openCreate(context),
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Text(
              'Your identity in chats — the character knows who you are.',
              style: TextStyle(color: kMuted, fontSize: 13),
            ),
          ),
          const Divider(color: kBorder),
          Expanded(
            child: ap.personas.isEmpty
                ? const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.person_pin_outlined, color: kMuted, size: 48),
                        SizedBox(height: 12),
                        Text('No personas yet — create one to give characters context about you.',
                            style: TextStyle(color: kMuted), textAlign: TextAlign.center),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: ap.personas.length,
                    itemBuilder: (_, i) {
                      final p = ap.personas[i];
                      final isActive = p.id == ap.settings.activePersonaId;
                      return _PersonaCard(
                        persona: p,
                        isActive: isActive,
                        onToggle: () => isActive ? ap.deactivatePersona() : ap.setActivePersona(p.id),
                        onEdit: () => _openEdit(context, p),
                        onDelete: () => _confirmDelete(context, p),
                      );
                    },
                  ),
          ),
        ],
      ),
      floatingActionButton: Container(
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [kCyan, kPrimary]),
          borderRadius: BorderRadius.circular(18),
          boxShadow: [BoxShadow(color: kCyan.withOpacity(0.35), blurRadius: 16, offset: const Offset(0, 6))],
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

class _PersonaCard extends StatelessWidget {
  final Persona persona;
  final bool isActive;
  final VoidCallback onToggle, onEdit, onDelete;
  const _PersonaCard({required this.persona, required this.isActive, required this.onToggle, required this.onEdit, required this.onDelete});

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 12),
    decoration: BoxDecoration(
      gradient: LinearGradient(
        colors: [(isActive ? kCyan : kPrimary).withOpacity(0.14), kCard],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: (isActive ? kCyan : kBorder).withOpacity(isActive ? 0.6 : 1), width: 1),
    ),
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Container(
            width: 44, height: 44,
            decoration: BoxDecoration(
              gradient: isActive ? const LinearGradient(colors: [kCyan, kPrimary]) : gradientFor(persona.name),
              borderRadius: BorderRadius.circular(16),
              ),
            child: Center(
              child: Text(persona.name.isNotEmpty ? persona.name[0].toUpperCase() : '?',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 18)),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(persona.name, style: const TextStyle(color: kText, fontWeight: FontWeight.w600, fontSize: 15)),
                    if (isActive) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: kCyan.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: kCyan.withOpacity(0.5)),
                        ),
                        child: const Text('Active', style: TextStyle(color: kCyan, fontSize: 10, fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ],
                ),
                if (persona.traits.isNotEmpty)
                  Text(persona.traits.map((t) => '#$t').join('  '),
                      style: const TextStyle(color: kMuted, fontSize: 12)),
              ],
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              OutlinedButton(
                onPressed: onToggle,
                style: OutlinedButton.styleFrom(
                  foregroundColor: isActive ? kMuted : kPrimary,
                  side: BorderSide(color: isActive ? kBorder : kPrimary),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(isActive ? 'Deactivate' : 'Use', style: const TextStyle(fontSize: 12)),
              ),
              IconButton(icon: const Icon(Icons.edit_outlined, size: 18), onPressed: onEdit, color: kMuted),
              IconButton(icon: const Icon(Icons.delete_outline, size: 18), onPressed: onDelete, color: kDanger),
            ],
          ),
        ],
      ),
    ),
  );
}

// ── PersonaSheet ──────────────────────────────────────────────────────────────

class PersonaSheet extends StatefulWidget {
  final Persona? persona;
  final AppSettings settings;
  const PersonaSheet({super.key, this.persona, required this.settings});

  @override
  State<PersonaSheet> createState() => _PersonaSheetState();
}

class _PersonaSheetState extends State<PersonaSheet> {
  late final TextEditingController _name, _avatar, _appearance, _personality, _backstory, _traits;
  final Map<String, bool> _generating = {};

  @override
  void initState() {
    super.initState();
    final p = widget.persona;
    _name        = TextEditingController(text: p?.name ?? '');
    _avatar      = TextEditingController(text: p?.avatar ?? '');
    _appearance  = TextEditingController(text: p?.appearance ?? '');
    _personality = TextEditingController(text: p?.personality ?? '');
    _backstory   = TextEditingController(text: p?.backstory ?? '');
    _traits      = TextEditingController(text: p?.traits.join(', ') ?? '');
  }

  @override
  void dispose() {
    for (final c in [_name, _avatar, _appearance, _personality, _backstory, _traits]) {
      c.dispose();
    }
    super.dispose();
  }

  String get _nameStr => _name.text.trim().isEmpty ? 'this persona' : _name.text.trim();

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
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
    } finally {
      if (mounted) setState(() => _generating[key] = false);
    }
  }

  void _genAppearance() => _generate('appearance', _appearance,
      'Describe the physical appearance of a person named $_nameStr in 2-3 sentences. Include height, build, hair, eyes, and clothing. Return only the description.');

  void _genPersonality() => _generate('personality', _personality,
      'Describe the personality of a person named $_nameStr in 2-3 sentences. Include communication style and emotional disposition. Return only the description.');

  void _genBackstory() => _generate('backstory', _backstory,
      'Write a short backstory for $_nameStr.'
      '${_appearance.text.isNotEmpty ? ' Appearance: ${_appearance.text.substring(0, _appearance.text.length.clamp(0, 200))}.' : ''}'
      '${_personality.text.isNotEmpty ? ' Personality: ${_personality.text.substring(0, _personality.text.length.clamp(0, 200))}.' : ''}'
      ' 2-3 sentences, grounded. Return only the backstory.');

  void _autofill() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter a name first.')));
      return;
    }
    await _generate('appearance', _appearance,
        'Describe the physical appearance of ${_nameStr} in 2-3 sentences. Return only the description.');
    _genPersonality();
    _genBackstory();
  }

  Persona _buildPersona() {
    final p = widget.persona;
    final traitsList = _traits.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();
    return Persona(
      id: p?.id ?? const Uuid().v4(),
      name: _name.text.trim().isEmpty ? 'Unnamed' : _name.text.trim(),
      avatar: _avatar.text.trim(),
      appearance: _appearance.text.trim(),
      personality: _personality.text.trim(),
      backstory: _backstory.text.trim(),
      traits: traitsList,
    );
  }

  Widget _genBtn(String key, VoidCallback fn) => IconButton(
    icon: _generating[key] == true
        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: kPrimary))
        : const Icon(Icons.auto_awesome, size: 18),
    onPressed: _generating[key] == true ? null : fn,
    color: kPrimary,
  );

  Widget _field(String label, TextEditingController ctrl, String key, VoidCallback genFn, {int maxLines = 3, String hint = ''}) =>
      Column(
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

  @override
  Widget build(BuildContext context) => DraggableScrollableSheet(
    initialChildSize: 0.9,
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
                Text(widget.persona != null ? 'Edit Persona' : 'New Persona',
                    style: const TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 17)),
                const Spacer(),
                TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                const SizedBox(width: 4),
                ElevatedButton(
                  onPressed: () => Navigator.pop(context, _buildPersona()),
                  child: const Text('Save'),
                ),
              ],
            ),
          ),
          const Divider(color: kBorder, height: 16),
          Expanded(
            child: ListView(
              controller: scrollController,
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
              children: [
                TextField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Name *', hintText: 'What the AI calls you'),
                  style: const TextStyle(color: kText),
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
                  label: const Text('Auto-fill from name'),
                  onPressed: _autofill,
                ),
                const SizedBox(height: 20),
                _field('Appearance', _appearance, 'appearance', _genAppearance, hint: 'Height, build, hair, eyes, clothing…'),
                _field('Personality', _personality, 'personality', _genPersonality, hint: 'How you come across — calm, sarcastic, warm…'),
                _field('Backstory', _backstory, 'backstory', _genBackstory, hint: 'Background the character should know…'),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Traits', style: TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 4),
                    TextField(
                      controller: _traits,
                      decoration: const InputDecoration(hintText: 'e.g. curious, protective, sarcastic (comma-separated)'),
                      style: const TextStyle(color: kText, fontSize: 13),
                    ),
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
