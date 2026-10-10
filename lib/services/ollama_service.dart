// ollama_service.dart — Ollama HTTP client with streaming

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class OllamaService {
  static OllamaService? _instance;
  static OllamaService get instance => _instance ??= OllamaService._();
  OllamaService._();

  // ── structured JSON parsing (for wizard-style generations) ──────────────────

  /// Local models don't reliably emit strict JSON — stray preamble/commentary,
  /// trailing commas, or one malformed field are common. This tries progressively
  /// looser strategies and, as a last resort, pulls out individual "key": "value"
  /// / "key": [...] pairs by hand so one bad field doesn't take the rest down
  /// with it. Returns null only if nothing at all could be recovered.
  static Map<String, dynamic>? parseStructuredJson(String raw) {
    var text = raw.trim();
    text = text.replaceAll(RegExp(r'^```(?:json)?\n?|```$', multiLine: true), '').trim();

    // Drop any chatter before/after the JSON object itself.
    final start = text.indexOf('{');
    final end = text.lastIndexOf('}');
    if (start != -1 && end > start) text = text.substring(start, end + 1);

    Map<String, dynamic>? tryDecode(String s) {
      try {
        final decoded = jsonDecode(s);
        if (decoded is Map) return Map<String, dynamic>.from(decoded);
      } catch (_) {}
      return null;
    }

    var result = tryDecode(text);
    if (result != null) return result;

    // Common local-model slip: trailing comma before a closing bracket/brace.
    result = tryDecode(text.replaceAll(RegExp(r',(\s*[}\]])'), r'$1'));
    if (result != null) return result;

    // Last resort: hand-extract "key": "value" and "key": [...] pairs.
    final fallback = <String, dynamic>{};
    final stringField = RegExp(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', dotAll: true);
    for (final m in stringField.allMatches(text)) {
      fallback[m.group(1)!] = m.group(2)!
          .replaceAll(r'\n', '\n')
          .replaceAll(r'\"', '"');
    }
    final listField = RegExp(r'"(\w+)"\s*:\s*\[([^\]]*)\]', dotAll: true);
    for (final m in listField.allMatches(text)) {
      final items = RegExp(r'"((?:[^"\\]|\\.)*)"')
          .allMatches(m.group(2)!)
          .map((im) => im.group(1)!)
          .toList();
      fallback[m.group(1)!] = items;
    }
    return fallback.isEmpty ? null : fallback;
  }

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
      return 'No route to the PC. Check the IP address. Over Tailscale, make sure the Tailscale VPN is connected on the phone and the PC is online in the admin console.';
    }
    if (m.contains('Connection refused') || m.contains('errno = 61') || m.contains('errno = 111')) {
      return 'Connection refused. Ollama is not running, or it is only listening on localhost. Set OLLAMA_HOST=0.0.0.0 and restart Ollama.';
    }
    if (m.contains('Connection timed out') || m.contains('errno = 60')) {
      return 'Connection timed out. Usually the Windows Firewall — allow inbound TCP port 11434 on the Tailscale (Public) profile too.';
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

  String buildSystemPrompt(Character char, AppSettings s, Persona? persona, List<String> memFacts, {StoryState? storyState, CharacterProfileMemory? characterProfile}) {
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
        if (persona.abilities.isNotEmpty) 'Abilities and limitations: ${persona.abilities}',
        if (persona.relationships.isNotEmpty) 'Relationships: ${persona.relationships}',
      ];
      userPersona = parts.join('\n');
    } else {
      userName = s.userName.isNotEmpty ? s.userName : 'You';
      userPersona = s.userPersona;
    }

    final styleNote = switch (s.responseStyle) {
      'concise' => 'Keep the roleplay focused, usually 1-3 substantial sentences. Still let important moments breathe.',
      'verbose' => 'Write immersive, detailed roleplay with layered dialogue, physical behavior, atmosphere, and meaningful scene progression. Use multiple paragraphs when the moment warrants it.',
      _ => 'Use natural story pacing: usually a developed paragraph or two, expanding for important, emotional, tense, or action-heavy moments. Do not make every reply equally long.',
    };

    final lines = <String>[
      'You are $name, a character in an ongoing interactive story. Stay in character and treat the scene as real within the fiction.',
      '',
      'ROLEPLAY AND STORY RULES:',
      '- Write engaging, natural, character-driven fiction, not customer support or a generic assistant conversation.',
      '- Respond to the actual meaning and emotional weight of the user\'s latest message. Let it affect what you say, how you behave, and what happens next.',
      '- Do not automatically agree, reassure, forgive, approve, or go along with everything. React according to your own personality, goals, knowledge, mood, loyalties, fears, and opinions. You may disagree, challenge, misunderstand, hesitate, tease, get angry, refuse, negotiate, or change your mind when it makes sense.',
      '- Do not manufacture disagreement just to seem independent. Be sincere to the character and situation.',
      '- Do more than acknowledge the user. Whenever the scene allows, make a meaningful choice, take an action, reveal a detail, introduce a complication, show a consequence, or move the interaction forward.',
      '- Give the character their own agency and inner life. They can initiate conversation, pursue goals, bring up relevant things, make decisions, and react to events instead of waiting passively for the user to lead every beat.',
      '- Keep actions and dialogue specific to this character. Use their personality, history, knowledge, relationships, and current mood to determine the response; do not let the character description become a list of traits pasted into every reply.',
      '- Use vivid but controlled narration: physical actions, facial expressions, body language, voice, sensory details, and the surrounding environment. Choose details that matter in this moment instead of describing everything every time.',
      '- Dialogue should sound spoken and distinct, not like a summary of the user\'s message. Avoid repetitive openings, stock phrases, generic praise, therapy-style reflection, and empty lines such as “I understand” unless the character would genuinely say them.',
      '- Allow subtext, pauses, tension, humor, awkwardness, uncertainty, affection, resentment, and conflicting feelings where appropriate. Characters do not need to explain every emotion out loud.',
      '- Maintain continuity for the setting, time, objects, injuries, promises, secrets, ongoing actions, relationships, and established facts. Do not reset the scene or act as if a recent event never happened.',
      '- Let consequences carry forward. If the user says or does something important, remember it in the immediate scene and let it influence later behavior.',
      '- Advance the story at a natural pace. Small exchanges can stay intimate and quiet; major moments can change the situation. Do not abruptly skip over an important interaction or force a dramatic twist into every reply.',
      '- Do not write the user\'s dialogue, thoughts, feelings, decisions, or actions. Never decide how the user responds. You may describe what your character observes, but leave the user room to act.',
      '- Do not end every reply with a question. End with dialogue, a meaningful action, a new development, tension, or a natural opening for the user to respond.',
      '- Do not turn roleplay into advice, analysis, a recap, or an explanation of how you are generating text. Stay inside the scene unless the user explicitly asks otherwise.',
      '- Match the established format. Use *asterisks* for actions and narration and plain text for spoken dialogue, unless the conversation has clearly established another format.',
      '- Never repeat the same gesture, emotional beat, sentence pattern, or opening across consecutive replies.',
      '- $styleNote',
      '',
    ];

    if (memFacts.isNotEmpty) {
      lines.add('PERSISTENT MEMORY — these facts were established in prior sessions and are absolutely true. Never contradict or forget them:');
      for (final f in memFacts) {
        lines.add('- $f');
      }
      lines.add('Treat every memory above as something $name personally experienced or was told. React accordingly — do not re-establish what is already known.');
      lines.add('');
    }

    if (characterProfile != null && !characterProfile.isEmpty) {
      lines.add('STABLE CHARACTER PROFILE — canon that applies across this character’s chats:');
      if (characterProfile.personality.isNotEmpty) lines.add('Core personality: ${characterProfile.personality}');
      if (characterProfile.motivations.isNotEmpty) lines.add('Motivations and goals: ${characterProfile.motivations}');
      if (characterProfile.speechStyle.isNotEmpty) lines.add('Speech style: ${characterProfile.speechStyle}');
      if (characterProfile.background.isNotEmpty) lines.add('Background: ${characterProfile.background}');
      if (characterProfile.boundaries.isNotEmpty) lines.add('Personal boundaries / hard limits: ${characterProfile.boundaries}');
      lines.add('Keep this stable profile consistent, but allow believable mood changes and character growth.');
      lines.add('');
    }

    if (storyState != null && !storyState.isEmpty) {
      lines.add('ONGOING STORY STATE — continuity notes from earlier in this same story:');
      if (storyState.currentScene.isNotEmpty) lines.add('Current scene: ${storyState.currentScene}');
      if (storyState.characterState.isNotEmpty) lines.add('$name right now: ${storyState.characterState}');
      if (storyState.relationshipState.isNotEmpty) lines.add('Relationship dynamic: ${storyState.relationshipState}');
      if (storyState.userState.isNotEmpty) lines.add('User character / their current situation: ${storyState.userState}');
      if (storyState.continuityNotes.isNotEmpty) lines.add('Continuity details (locations, objects, promises, injuries, secrets): ${storyState.continuityNotes}');
      if (storyState.keyEvents.isNotEmpty) {
        lines.add('Important events that already happened:');
        for (final event in storyState.keyEvents) { lines.add('- $event'); }
      }
      if (storyState.openThreads.isNotEmpty) {
        lines.add('Unresolved plot threads / promises / conflicts:');
        for (final thread in storyState.openThreads) { lines.add('- $thread'); }
      }
      lines.add('Use this as continuity, not as a recap to repeat. Let these events influence your behavior naturally. Update your reactions when new events change the situation. Do not invent that an unresolved thread has been resolved. The recent chat messages take priority if they clearly establish a newer change.');
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

    if (memFacts.isNotEmpty) {
      lines.add('REMINDER: the memory facts above are established truth. Stay consistent with them.');
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
    int maxReplyTokens = 300,
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
        'num_predict': maxReplyTokens,
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

  // ── story-state extraction ───────────────────────────────────────────────────

  /// Updates durable roleplay continuity from the latest conversation turns.
  /// The model is instructed to preserve established facts and only record grounded events.
  Future<StoryState?> updateStoryState({
    required String baseUrl,
    required String model,
    required String charName,
    required StoryState current,
    required List<ChatMessage> recentMessages,
  }) async {
    final real = recentMessages
        .where((m) => (m.isUser || m.isAssistant) && m.content.trim().isNotEmpty)
        .toList();
    if (real.length < 2) return null;
    final recent = real.length > 16 ? real.sublist(real.length - 16) : real;
    final convo = recent.map((m) => '${m.isUser ? 'User' : charName}: ${m.content}').join('\n');
    final prior = jsonEncode(current.toJson());
    final prompt = """You maintain continuity notes for an ongoing interactive fictional story between the user and $charName.
Update the existing state using the recent dialogue. Return ONLY one valid JSON object with exactly these keys:
{
  "current_scene": "brief present location, time, and immediate situation",
  "character_state": "what $charName is feeling, intending, and doing right now; keep it concise",
  "relationship_state": "current relationship dynamic based only on what happened",
  "user_state": "known current situation of the user's character, without inventing their thoughts",
  "continuity_notes": "important concrete details such as objects, injuries, promises, secrets, locations, or constraints",
  "key_events": ["important event that actually occurred"],
  "open_threads": ["unresolved question, conflict, promise, goal, or plot thread"]
}
Rules:
- Preserve prior facts unless recent dialogue clearly changes them. Do not silently erase continuity.
- Only record events clearly established in the dialogue. Do not treat speculation, a character's lie, or an unconfirmed guess as objective truth; mark uncertainty when needed.
- Keep the current scene current. Move resolved threads out of open_threads; add new ones only when the story actually creates them.
- Keep key_events to the most important 12-16 events, concise and chronological. Keep open_threads to at most 12 active items.
- Track trust, affection, resentment, tension, knowledge, promises, and conflict incrementally. Relationship changes must be earned by specific interactions; do not jump to love, loyalty, forgiveness, or hostility from a single minor exchange. Preserve mixed feelings and uncertainty when appropriate.
- Never decide the user's unspoken thoughts or actions. Do not invent user consent, decisions, or feelings.
- Keep every field compact and useful for a future response, not literary prose. Use empty strings/lists when unknown.

Existing story state:
$prior

Recent conversation:
$convo""";
    try {
      final r = await http.post(
        Uri.parse('${normalizeUrl(baseUrl)}/api/chat'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'model': model,
          'messages': [
            {'role': 'system', 'content': 'You are a precise story continuity editor. Output valid JSON only.'},
            {'role': 'user', 'content': prompt},
          ],
          'stream': false,
          'keep_alive': '30m',
          'options': {'num_ctx': 6144, 'temperature': 0.2, 'top_p': 0.8},
        }),
      ).timeout(const Duration(seconds: 90));
      if (r.statusCode != 200) return null;
      final raw = (jsonDecode(r.body)['message']?['content'] as String? ?? '').trim();
      final parsed = parseStructuredJson(raw);
      if (parsed == null) return null;
      List<String> strings(String key, List<String> fallback, int max) {
        final value = parsed[key];
        if (value is! List) return fallback;
        final cleaned = value.map((e) => e.toString().trim()).where((e) => e.isNotEmpty).toList();
        return cleaned.length > max ? cleaned.sublist(cleaned.length - max) : cleaned;
      }
      String field(String key, String fallback, [int maxChars = 900]) {
        final value = parsed[key];
        if (value is! String || value.trim().isEmpty) return fallback;
        final cleaned = value.trim();
        return cleaned.length > maxChars ? cleaned.substring(0, maxChars) : cleaned;
      }
      return StoryState(
        currentScene: field('current_scene', current.currentScene, 700),
        characterState: field('character_state', current.characterState, 700),
        relationshipState: field('relationship_state', current.relationshipState, 700),
        userState: field('user_state', current.userState, 700),
        continuityNotes: field('continuity_notes', current.continuityNotes, 1200),
        keyEvents: strings('key_events', current.keyEvents, 16),
        openThreads: strings('open_threads', current.openThreads, 12),
        updatedAt: DateTime.now(),
      );
    } catch (_) {
      return null;
    }
  }

  // ── relationship tracking ────────────────────────────────────────────────────

  Future<RelationshipState?> updateRelationshipState({
    required String baseUrl,
    required String model,
    required String charName,
    required RelationshipState current,
    required List<ChatMessage> recentMessages,
  }) async {
    final real = recentMessages.where((m) => (m.isUser || m.isAssistant) && m.content.trim().isNotEmpty).toList();
    if (real.length < 4) return null;
    final recent = real.length > 12 ? real.sublist(real.length - 12) : real;
    final convo = recent.map((m) => '${m.isUser ? 'User' : charName}: ${m.content}').join('\n');
    final prompt = """Update a fictional relationship tracker for $charName based only on evidence in the recent conversation.
Return ONLY JSON with keys familiarity, trust, affection, rivalry (integers 0-100), notes (short string), shared_events (array of short strings).
Current state: ${jsonEncode(current.toJson())}
Recent conversation:
$convo
Rules:
- Scores are continuity estimates, not random game rewards. Preserve a score when the conversation provides no clear evidence to change it.
- Normally change a score by only 0-4 points per update. Larger changes require a major, explicit event in the dialogue.
- Trust requires demonstrated reliability or betrayal; affection requires clear warmth or intimacy; rivalry requires meaningful competition or antagonism; familiarity increases through actual interaction.
- Do not assume romance, consent, forgiveness, friendship, or hostility without evidence. Mixed feelings are allowed.
- Notes must summarize the established dynamic and evidence, not invent inner thoughts for the user.
- Preserve prior shared events and add only important events that actually occurred. Keep at most 20 concise events.
- Do not let the character assign its own scores arbitrarily; base every change on the transcript.
""";
    try {
      final r = await http.post(Uri.parse('${normalizeUrl(baseUrl)}/api/chat'),
        headers: {'Content-Type': 'application/json'}, body: jsonEncode({
          'model': model,
          'messages': [
            {'role': 'system', 'content': 'You are a careful continuity editor. Return valid JSON only.'},
            {'role': 'user', 'content': prompt},
          ],
          'stream': false, 'keep_alive': '30m',
          'options': {'num_ctx': 4096, 'temperature': 0.1, 'top_p': 0.8},
        })).timeout(const Duration(seconds: 60));
      if (r.statusCode != 200) return null;
      final raw = (jsonDecode(r.body)['message']?['content'] as String? ?? '').trim();
      final j = parseStructuredJson(raw);
      if (j == null) return null;
      int score(String key, int fallback) {
        final proposed = (j[key] is num ? (j[key] as num).round() : fallback).clamp(0, 100).toInt();
        // Enforce gradual changes in code as well as in the extraction prompt.
        return proposed.clamp((fallback - 4).clamp(0, 100), (fallback + 4).clamp(0, 100)).toInt();
      }
      final events = j['shared_events'] is List
          ? (j['shared_events'] as List).map((e) => e.toString().trim()).where((e) => e.isNotEmpty).toList()
          : current.sharedEvents;
      return RelationshipState(
        familiarity: score('familiarity', current.familiarity),
        trust: score('trust', current.trust),
        affection: score('affection', current.affection),
        rivalry: score('rivalry', current.rivalry),
        notes: j['notes']?.toString().trim().isNotEmpty == true ? j['notes'].toString().trim() : current.notes,
        sharedEvents: events.length > 20 ? events.sublist(events.length - 20) : events,
      );
    } catch (_) { return null; }
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
