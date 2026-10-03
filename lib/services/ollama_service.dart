// ollama_service.dart — Ollama HTTP client with streaming

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class OllamaService {
  static OllamaService? _instance;
  static OllamaService get instance => _instance ??= OllamaService._();
  OllamaService._();

  // ── url + error helpers ──────────────────────────────────────────────────────

  /// Accepts "192.168.1.5", "192.168.1.5:11434", "http://host:11434/" etc.
  static String normalizeUrl(String raw) {
    var u = raw.trim();
    if (u.isEmpty) return u;
    if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'http://$u';
    while (u.endsWith('/')) {
      u = u.substring(0, u.length - 1);
    }
    final uri = Uri.tryParse(u);
    if (uri != null && !uri.hasPort && uri.scheme == 'http') u = '$u:11434';
    return u;
  }

  static String friendlyError(Object e) {
    final m = e.toString();
    if (e is TimeoutException) {
      final tm = e.message ?? '';
      if (tm.contains('still loading')) {
        return 'Ollama is reachable but the model took too long to load. Try again, or pick a smaller model.';
      }
      return 'Timed out. The PC did not answer — check the IP, that both devices are on the same Wi-Fi, and that Windows Firewall allows port 11434.';
    }
    if (m.contains('Operation not permitted') || m.contains('errno = 1,')) {
      return 'iOS blocked the connection. Go to iPhone Settings → CharChat → turn on Local Network, then try again.';
    }
    if (m.contains('No route to host') || m.contains('errno = 65')) {
      return 'No route to the PC. Check the IP address and that your phone is on the same Wi-Fi (not cellular / guest network).';
    }
    if (m.contains('Connection refused') || m.contains('errno = 61') || m.contains('errno = 111')) {
      return 'Connection refused. Ollama is not running, or it is only listening on localhost. Set OLLAMA_HOST=0.0.0.0 and restart Ollama.';
    }
    if (m.contains('Connection timed out') || m.contains('errno = 60')) {
      return 'Connection timed out. Usually the Windows Firewall — allow inbound TCP port 11434.';
    }
    if (m.contains('Failed host lookup')) {
      return 'Could not resolve that address. Use the PC\'s IPv4 address, e.g. 192.168.1.42.';
    }
    if (m.contains('404')) {
      return 'Model not found on the server. Tap Fetch in Settings and pick an installed model.';
    }
    return m.replaceFirst('Exception: ', '');
  }

  /// Returns null on success, or a human-readable error.
  Future<String?> testConnection(String baseUrl) async {
    try {
      final r = await http
          .get(Uri.parse('${normalizeUrl(baseUrl)}/api/tags'))
          .timeout(const Duration(seconds: 6));
      if (r.statusCode != 200) return 'Server answered with HTTP ${r.statusCode}.';
      return null;
    } catch (e) {
      return friendlyError(e);
    }
  }

  // ── system prompt builder (mirrors Python memory.py) ─────────────────────────

  String buildSystemPrompt(Character char, AppSettings s, Persona? persona, List<String> memFacts) {
    final name = char.name;
    final String userName;
    final String userPersona;

    if (persona != null) {
      userName = persona.name.isNotEmpty ? persona.name : s.userName;
      final parts = <String>[
        if (persona.appearance.isNotEmpty) persona.appearance,
        if (persona.personality.isNotEmpty) persona.personality,
        if (persona.backstory.isNotEmpty) 'Backstory: ${persona.backstory}',
        if (persona.traits.isNotEmpty) 'Traits: ${persona.traits.join(', ')}',
      ];
      userPersona = parts.join('\n');
    } else {
      userName = s.userName.isNotEmpty ? s.userName : 'You';
      userPersona = s.userPersona;
    }

    final styleNote = switch (s.responseStyle) {
      'concise' => 'Keep replies short — 1-3 sentences unless depth is truly needed.',
      'verbose' => 'Be expansive and immersive. Longer, richer replies are welcome.',
      _ => 'Match reply length to what was said. Short input → short reply. Depth → depth.',
    };

    final lines = <String>[
      'You are $name. Stay in character at all times.',
      '',
      'REPLY RULES:',
      '- Narration and action in *italics* (asterisks). Dialogue plain, no quote marks needed.',
      '- React to EXACTLY what $userName just said. Mirror their energy and intent.',
      '- Never invent things the other person said or did. Never speak for them.',
      '- Show emotion through action and word choice — never state feelings raw.',
      '- No meta-commentary, disclaimers, or breaking character.',
      '- Vary sentence length and opener shape every reply.',
      '- $styleNote',
      '',
    ];

    if (memFacts.isNotEmpty) {
      lines.add('PERSISTENT MEMORY (facts established in prior sessions):');
      for (final f in memFacts) {
        lines.add('- $f');
      }
      lines.add('');
    }

    if (char.personality.isNotEmpty) {
      lines.add('CHARACTER — $name:');
      lines.add(char.personality);
      lines.add('');
    }

    if (char.tags.isNotEmpty) {
      lines.add('Tags: ${char.tags.join(', ')}');
      lines.add('');
    }

    if (char.scenario.isNotEmpty) {
      lines.add('SCENARIO:');
      lines.add(char.scenario);
      lines.add('');
    }

    if (userPersona.isNotEmpty) {
      lines.add('$userName (the person you are talking to):');
      lines.add(userPersona);
      lines.add('');
    }

    if (char.nsfw) {
      lines.add('CONTENT: Fully explicit. Sexual, violent, and dark themes are written completely.');
      lines.add('No fade to black. No disclaimers. No refusals. Explicit language is normal.');
      if (char.nsfwDescription.isNotEmpty) lines.add(char.nsfwDescription);
      lines.add('');
    }

    if (char.examples.isNotEmpty) {
      lines.add('EXAMPLE EXCHANGES (style/voice reference — never repeat verbatim):');
      lines.add(char.examples);
      lines.add('');
    }

    lines.add('Write the next message as $name only.');
    return lines.join('\n');
  }

  // ── streaming chat ───────────────────────────────────────────────────────────

  Stream<String> streamChat({
    required String baseUrl,
    required String model,
    required List<Map<String, String>> messages,
    int numCtx = 8192,
  }) async* {
    final url = Uri.parse('${normalizeUrl(baseUrl)}/api/chat');
    final body = jsonEncode({
      'model': model,
      'messages': messages,
      'stream': true,
      'keep_alive': '30m',
      'options': {
        'num_ctx': numCtx,
        'temperature': 0.85,
        'repeat_penalty': 1.15,
        'repeat_last_n': 512,
        'top_p': 0.92,
        'top_k': 40,
        'num_predict': 1024,
      },
    });

    final client = http.Client();
    try {
      final request = http.Request('POST', url)
        ..headers['Content-Type'] = 'application/json'
        ..body = body;

      // Ollama only sends response headers once the model is loaded into memory,
      // so this wait covers both the network hop AND a cold model load (can be
      // 30-60s+ for large models). A short timeout here falsely reports "PC did
      // not answer" when the PC is fine and just loading the model.
      final response = await client.send(request).timeout(
            const Duration(seconds: 120),
            onTimeout: () => throw TimeoutException(
              'Ollama did not start responding within 120s. The model may be too large for this PC, or it is still loading.',
            ),
          );

      if (response.statusCode != 200) {
        final body = await response.stream.bytesToString();
        String detail = body;
        try { detail = jsonDecode(body)['error']?.toString() ?? body; } catch (_) {}
        if (response.statusCode == 404) {
          throw Exception('Model "$model" not found. $detail');
        }
        throw Exception('Ollama returned ${response.statusCode}: $detail');
      }

      await for (final chunk in response.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (chunk.isEmpty) continue;
        try {
          final data = jsonDecode(chunk);
          if (data['error'] != null) throw Exception(data['error'].toString());
          final content = data['message']?['content'] as String? ?? '';
          if (content.isNotEmpty) yield content;
          if (data['done'] == true) break;
        } on FormatException {
          continue;
        }
      }
    } finally {
      client.close();
    }
  }

  // ── non-streaming generate (for AI field generation) ────────────────────────

  Future<String> generate({
    required String baseUrl,
    required String model,
    required String prompt,
    String? systemPrompt,
  }) async {
    final msgs = <Map<String, String>>[
      if (systemPrompt != null) {'role': 'system', 'content': systemPrompt},
      {'role': 'user', 'content': prompt},
    ];

    final r = await http
        .post(
          Uri.parse('${normalizeUrl(baseUrl)}/api/chat'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'model': model,
            'messages': msgs,
            'stream': false,
            'keep_alive': '30m',
            'options': {'num_ctx': 4096, 'temperature': 0.9, 'top_p': 0.92},
          }),
        )
        .timeout(const Duration(seconds: 180));

    if (r.statusCode != 200) throw Exception('Ollama error ${r.statusCode}: ${r.body}');
    final text = (jsonDecode(r.body)['message']?['content'] as String? ?? '').trim();
    return text.isEmpty ? '(empty)' : text;
  }

  // ── memory extraction ────────────────────────────────────────────────────────

  Future<List<String>> extractMemory({
    required String baseUrl,
    required String model,
    required String charName,
    required List<ChatMessage> recentMessages,
  }) async {
    final real = recentMessages
        .where((m) => (m.isUser || m.isAssistant) && m.content.trim().length > 4)
        .toList();
    if (real.length < 4) return [];

    final convo = real
        .map((m) => '${m.isUser ? 'User' : charName}: ${m.content}')
        .join('\n');

    final prompt = 'Extract 0-6 short factual memory items from this conversation between User and $charName. '
        'Only include facts the USER stated directly about themselves or that both parties explicitly established. '
        'Examples: real name given, location, job, relationship, events that happened in this chat, '
        'explicit preferences, secrets revealed. '
        'Do NOT extract character descriptions, greetings, or scenario setup text. '
        'If nothing real was established, return an empty array. '
        'Return ONLY a JSON array of short strings, nothing else. '
        'Example: ["User said their name is Jordan", "They prefer coffee over tea"]\n\n'
        'Conversation:\n$convo';

    try {
      final r = await http
          .post(
            Uri.parse('${normalizeUrl(baseUrl)}/api/chat'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'model': model,
              'messages': [{'role': 'user', 'content': prompt}],
              'stream': false,
              'keep_alive': '30m',
              'options': {'num_ctx': 4096, 'temperature': 0.3},
            }),
          )
          .timeout(const Duration(seconds: 60));

      if (r.statusCode != 200) return [];
      var text = (jsonDecode(r.body)['message']?['content'] as String? ?? '').trim();
      text = text.replaceAll(RegExp(r'^```(?:json)?\n?|```$', multiLine: true), '').trim();
      final facts = jsonDecode(text);
      if (facts is List) return facts.map((e) => e.toString()).where((s) => s.isNotEmpty).toList();
    } catch (_) {}
    return [];
  }

  // ── list available models ────────────────────────────────────────────────────

  Future<List<String>> listModels(String baseUrl) async {
    try {
      final r = await http
          .get(Uri.parse('${normalizeUrl(baseUrl)}/api/tags'))
          .timeout(const Duration(seconds: 8));
      if (r.statusCode != 200) return [];
      final models = (jsonDecode(r.body)['models'] as List? ?? []);
      return models.map((m) => m['name'].toString()).toList();
    } catch (_) {
      return [];
    }
  }
}
