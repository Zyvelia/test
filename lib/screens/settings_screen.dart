// settings_screen.dart

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/app_provider.dart';
import '../services/auth_service.dart';
import '../services/ollama_service.dart';
import '../theme.dart';
import 'login_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _url      = TextEditingController();
  final _model    = TextEditingController();
  final _username = TextEditingController();
  final _persona  = TextEditingController();
  String _style   = 'balanced';
  double _ctx     = 40;
  double _maxReply = 650;
  bool _haptic = true;
  String _modelHint = '';
  bool _fetching  = false;
  bool _testing   = false;
  String? _status;        // result of connection test
  bool _statusOk  = false;
  List<String> _models = [];

  @override
  void initState() {
    super.initState();
    final s = context.read<AppProvider>().settings;
    _url.text      = s.ollamaUrl;
    _model.text    = s.model;
    _username.text = s.userName;
    _persona.text  = s.userPersona;
    _style         = s.responseStyle;
    _ctx           = s.contextWindow.toDouble();
    _maxReply      = s.maxReplyTokens.toDouble();
    _haptic        = s.hapticOnSend;
  }

  @override
  void dispose() {
    _url.dispose(); _model.dispose(); _username.dispose(); _persona.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() { _testing = true; _status = null; });
    final err = await OllamaService.instance.testConnection(_url.text);
    if (!mounted) return;
    setState(() {
      _testing = false;
      _statusOk = err == null;
      _status = err ?? 'Connected to ${OllamaService.normalizeUrl(_url.text)}';
    });
    if (err == null) {
      // Save the working URL right away so chat and AI buttons use it.
      await _fetchModels();
      if (mounted) _save();
    }
  }

  Future<void> _fetchModels() async {
    setState(() { _fetching = true; _modelHint = ''; });
    final models = await OllamaService.instance.listModels(_url.text);
    if (!mounted) return;
    setState(() {
      _fetching = false;
      _models = models;
      if (models.isEmpty) {
        _modelHint = 'No models found. Run "ollama pull <model>" on your PC first.';
      } else {
        _modelHint = '';
        if (_model.text.trim().isEmpty || !models.contains(_model.text.trim())) {
          // keep a valid choice selected
          if (_model.text.trim().isEmpty) _model.text = models.first;
        }
      }
    });
  }

  void _save() {
    final ap = context.read<AppProvider>();
    // Preserve appearance and activePersonaId — neither is editable on this screen.
    ap.saveSettings(AppSettings(
      ollamaUrl: _url.text.trim().isEmpty ? 'http://192.168.1.100:11434' : OllamaService.normalizeUrl(_url.text),
      model: _model.text.trim().isEmpty ? 'dolphin-mistral' : _model.text.trim(),
      userName: _username.text.trim().isEmpty ? 'You' : _username.text.trim(),
      userPersona: _persona.text.trim(),
      responseStyle: _style,
      contextWindow: _ctx.round(),
      maxReplyTokens: _maxReply.round(),
      hapticOnSend: _haptic,
      activePersonaId: ap.settings.activePersonaId,
      appearance: ap.settings.appearance,
    ));
    // Show the normalized URL so dj can confirm what was stored.
    _url.text = ap.settings.ollamaUrl;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Settings saved.'), behavior: SnackBarBehavior.floating),
    );
  }

  void _logout() {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Lock app'),
        content: const Text('Return to the lock screen?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () async {
              await AuthService.instance.logout();
              if (!mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (_) => false,
              );
            },
            child: const Text('Lock'),
          ),
        ],
      ),
    );
  }

  void _changePassword() async {
    final oldCtrl = TextEditingController();
    final newCtrl = TextEditingController();
    final con2    = TextEditingController();
    String? err;

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: const Text('Change password'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: oldCtrl,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Current password'),
                style: const TextStyle(color: kText),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: newCtrl,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'New password'),
                style: const TextStyle(color: kText),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: con2,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Confirm new password'),
                style: const TextStyle(color: kText),
              ),
              if (err != null) ...[
                const SizedBox(height: 8),
                Text(err!, style: const TextStyle(color: kDanger, fontSize: 12)),
              ],
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            TextButton(
              onPressed: () async {
                if (newCtrl.text != con2.text) {
                  setSt(() => err = 'Passwords do not match.');
                  return;
                }
                final result = await AuthService.instance.changePassword(
                  oldPassword: oldCtrl.text,
                  newPassword: newCtrl.text,
                );
                if (result == null) {
                  if (ctx.mounted) Navigator.pop(ctx);
                  if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Password changed.')));
                } else {
                  setSt(() => err = result);
                }
              },
              child: const Text('Change'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        title: const GradientText('Settings', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 26)),
        centerTitle: false,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: TextButton(
              onPressed: _save,
              style: TextButton.styleFrom(
                backgroundColor: kPrimary.withValues(alpha: 0.18),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(horizontal: 18),
              ),
              child: const Text('Save', style: TextStyle(color: kPrimary, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _section('Ollama Connection', [
            _row('Server URL', TextField(
              controller: _url,
              decoration: const InputDecoration(
                hintText: '100.x.y.z:11434 (Tailscale) or 192.168.1.42:11434',
                prefixIcon: Icon(Icons.dns_outlined, size: 18),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
              enableSuggestions: false,
              style: const TextStyle(color: kText, fontSize: 14),
            )),
            SizedBox(
              width: double.infinity,
              child: GradientButton(
                gradient: const LinearGradient(colors: [kCyan, kPrimary]),
                onPressed: _testing ? null : _testConnection,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _testing
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.wifi_tethering, size: 18),
                    const SizedBox(width: 8),
                    Text(_testing ? 'Testing…' : 'Test connection'),
                  ],
                ),
              ),
            ),
            if (_status != null)
              Container(
                margin: const EdgeInsets.only(top: 10),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: (_statusOk ? kGreen : kDanger).withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: (_statusOk ? kGreen : kDanger).withValues(alpha: 0.35)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(_statusOk ? Icons.check_circle : Icons.error_outline,
                        size: 16, color: _statusOk ? kGreen : kDanger),
                    const SizedBox(width: 8),
                    Expanded(child: Text(_status!,
                        style: TextStyle(color: _statusOk ? kGreen : kDanger, fontSize: 12.5, height: 1.4))),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            _row('Model', Row(
              children: [
                Expanded(child: TextField(
                  controller: _model,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: const InputDecoration(hintText: 'dolphin-mistral'),
                  style: const TextStyle(color: kText, fontSize: 14),
                )),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: _fetching ? null : _fetchModels,
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                    minimumSize: Size.zero,
                  ),
                  child: _fetching
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 1.5, color: kPrimary))
                      : const Text('Fetch', style: TextStyle(fontSize: 13)),
                ),
              ],
            )),
            if (_models.isNotEmpty)
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final m in _models)
                    ChoiceChip(
                      label: Text(m, style: TextStyle(fontSize: 12, color: _model.text.trim() == m ? kPrimary : kMuted)),
                      selected: _model.text.trim() == m,
                      onSelected: (_) => setState(() => _model.text = m),
                      selectedColor: kPrimary.withValues(alpha: 0.14),
                      backgroundColor: kSurface,
                      showCheckmark: false,
                      side: BorderSide(color: _model.text.trim() == m ? kPrimary : kBorder),
                    ),
                ],
              ),
            if (_modelHint.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(_modelHint, style: const TextStyle(color: kMuted, fontSize: 11.5)),
              ),
            const SizedBox(height: 12),
            const _HelpBox(),
          ]),
          const SizedBox(height: 24),
          _section('Identity', [
            _row('Your name', TextField(
              controller: _username,
              decoration: const InputDecoration(hintText: 'You'),
              style: const TextStyle(color: kText, fontSize: 13),
            )),
            _row('Fallback persona', TextField(
              controller: _persona,
              maxLines: 3,
              decoration: const InputDecoration(hintText: 'Description used when no persona is active'),
              style: const TextStyle(color: kText, fontSize: 13),
            )),
          ]),
          const SizedBox(height: 24),
          _section('Chat behavior', [
            _row('Response style', DropdownButtonFormField<String>(
              value: _style,
              items: ['concise', 'balanced', 'verbose']
                  .map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(color: kText))))
                  .toList(),
              onChanged: (v) { if (v != null) setState(() => _style = v); },
              decoration: const InputDecoration(),
              dropdownColor: kCard,
              style: const TextStyle(color: kText),
            )),
            _row('Context window (${_ctx.round()} msgs)',
              Slider(
                value: _ctx,
                min: 10,
                max: 200,
                divisions: 19,
                label: '${_ctx.round()}',
                onChanged: (v) => setState(() => _ctx = v),
                activeColor: kPrimary,
              ),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Haptic on send', style: TextStyle(color: kText, fontSize: 14)),
              subtitle: const Text('Vibrate when a message is sent', style: TextStyle(color: kMuted, fontSize: 12)),
              value: _haptic,
              onChanged: (v) => setState(() => _haptic = v),
              activeColor: kPrimary,
            ),
            _row('Max reply length (${_maxReply.round()} tokens)',
              Slider(
                value: _maxReply,
                min: 50,
                max: 1000,
                divisions: 19,
                label: '${_maxReply.round()}',
                onChanged: (v) => setState(() => _maxReply = v),
                activeColor: kAmber,
              ),
            ),
          ]),
          const SizedBox(height: 24),
          _section('Account', [
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Change password', style: TextStyle(color: kText, fontSize: 14)),
              leading: const Icon(Icons.lock_outline, color: kAmber, size: 20),
              onTap: _changePassword,
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Lock app', style: TextStyle(color: kText, fontSize: 14)),
              leading: const Icon(Icons.logout, color: kRose, size: 20),
              onTap: _logout,
            ),
          ]),
          const SizedBox(height: 40),
          const Center(
            child: Text('CharChat v2.0 · Ollama on local network',
                style: TextStyle(color: kMuted, fontSize: 11)),
          ),
        ],
      ),
    );
  }

  static const _meta = <String, List<Object>>{
    'Ollama Connection': [Icons.bolt_rounded, kCyan],
    'Identity': [Icons.face_rounded, kPrimary2],
    'Chat behavior': [Icons.forum_rounded, kAmber],
    'Account': [Icons.shield_rounded, kGreen],
  };

  Widget _section(String title, List<Widget> children) {
    final m = _meta[title] ?? [Icons.circle, kPrimary];
    final col = m[1] as Color;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: col.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(m[0] as IconData, size: 16, color: col),
            ),
            const SizedBox(width: 10),
            Text(title,
                style: TextStyle(color: col, fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 0.3)),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [col.withValues(alpha: 0.08), kCard],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: col.withValues(alpha: 0.28), width: 0.9),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
        ),
      ],
    );
  }

  Widget _row(String label, Widget child) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: kMuted, fontSize: 12, fontWeight: FontWeight.w500)),
        const SizedBox(height: 4),
        child,
      ],
    ),
  );
}

class _HelpBox extends StatelessWidget {
  const _HelpBox();

  @override
  Widget build(BuildContext context) => Theme(
    data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
    child: ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Can\'t connect? PC checklist',
          style: TextStyle(color: kTextSoft, fontSize: 13, fontWeight: FontWeight.w600)),
      iconColor: kMuted,
      collapsedIconColor: kMuted,
      children: const [
        _Step('1', 'Quit Ollama (system tray), then set a user environment variable OLLAMA_HOST = 0.0.0.0 and start Ollama again.'),
        _Step('2', 'Allow port 11434 in Windows Firewall, inbound TCP. Tailscale\'s adapter is often on the Public profile, so allow it on Public too, or scope the rule to remote address 100.64.0.0/10.'),
        _Step('3', 'Run `tailscale ip -4` on the PC and use that 100.x.y.z address (or the PC\'s MagicDNS name). Not \"localhost\".'),
        _Step('4', 'Tailscale must be connected on the phone too, and both devices must be on the same tailnet. Test in Safari: http://100.x.y.z:11434 should say \"Ollama is running\".'),
        _Step('5', 'iPhone Settings → CharChat → Local Network must be ON.'),
      ],
    ),
  );
}

class _Step extends StatelessWidget {
  final String n, text;
  const _Step(this.n, this.text);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 20, height: 20,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: kPrimary.withValues(alpha: 0.15), shape: BoxShape.circle),
          child: Text(n, style: const TextStyle(color: kPrimary, fontSize: 11, fontWeight: FontWeight.w700)),
        ),
        const SizedBox(width: 10),
        Expanded(child: Text(text, style: const TextStyle(color: kMuted, fontSize: 12.5, height: 1.45))),
      ],
    ),
  );
}
