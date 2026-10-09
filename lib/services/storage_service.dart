// storage_service.dart — JSON file persistence for characters, personas, chats, memories, sessions

import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import '../models/models.dart';

class StorageService {
  static StorageService? _instance;
  static StorageService get instance => _instance ??= StorageService._();
  StorageService._();

  late Directory _base;
  bool _ready = false;

  Future<void> init() async {
    if (_ready) return;
    final docs = await getApplicationDocumentsDirectory();
    _base = Directory('${docs.path}/charchat');
    await _base.create(recursive: true);
    await Directory('${_base.path}/characters').create(recursive: true);
    await Directory('${_base.path}/chats').create(recursive: true);
    await Directory('${_base.path}/memories').create(recursive: true);
    await Directory('${_base.path}/personas').create(recursive: true);
    await Directory('${_base.path}/sessions').create(recursive: true);
    _ready = true;
  }

  // ── helpers ─────────────────────────────────────────────────────────────────

  File _charFile(String id) => File('${_base.path}/characters/$id.json');
  File _chatFile(String id) => File('${_base.path}/chats/$id.json');
  File _memFile(String id) => File('${_base.path}/memories/$id.json');
  File _storyStateFile(String id) => File('${_base.path}/memories/${id}_story_state.json');
  File _personaFile(String id) => File('${_base.path}/personas/$id.json');
  File _sessionFile(String id) => File('${_base.path}/sessions/$id.json');
  File get _settingsFile => File('${_base.path}/settings.json');

  Map<String, dynamic> _readJson(File f) {
    try {
      if (f.existsSync()) return jsonDecode(f.readAsStringSync());
    } catch (_) {}
    return {};
  }

  List<dynamic> _readJsonList(File f) {
    try {
      if (f.existsSync()) return jsonDecode(f.readAsStringSync());
    } catch (_) {}
    return [];
  }

  void _writeJson(File f, dynamic data) =>
      f.writeAsStringSync(jsonEncode(data));

  // ── settings ────────────────────────────────────────────────────────────────

  AppSettings loadSettings() => AppSettings.fromJson(_readJson(_settingsFile));

  void saveSettings(AppSettings s) => _writeJson(_settingsFile, s.toJson());

  // ── characters ──────────────────────────────────────────────────────────────

  List<Character> loadCharacters() {
    final dir = Directory('${_base.path}/characters');
    if (!dir.existsSync()) return [];
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json'));
    return files
        .map((f) {
          try {
            return Character.fromJson(jsonDecode(f.readAsStringSync()));
          } catch (_) {
            return null;
          }
        })
        .whereType<Character>()
        .toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
  }

  void saveCharacter(Character c) =>
      _writeJson(_charFile(c.id), c.toJson());

  void deleteCharacter(String id) {
    for (final f in [_charFile(id), _chatFile(id), _memFile(id)]) {
      if (f.existsSync()) f.deleteSync();
    }
    // delete all sessions for this char
    final dir = Directory('${_base.path}/sessions');
    if (dir.existsSync()) {
      for (final f in dir.listSync().whereType<File>()) {
        try {
          final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
          if (j['char_id'] == id) f.deleteSync();
        } catch (_) {}
      }
    }
  }

  // ── personas ─────────────────────────────────────────────────────────────────

  List<Persona> loadPersonas() {
    final dir = Directory('${_base.path}/personas');
    if (!dir.existsSync()) return [];
    return dir
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.json'))
        .map((f) {
          try {
            return Persona.fromJson(jsonDecode(f.readAsStringSync()));
          } catch (_) {
            return null;
          }
        })
        .whereType<Persona>()
        .toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
  }

  void savePersona(Persona p) =>
      _writeJson(_personaFile(p.id), p.toJson());

  void deletePersona(String id) {
    if (_personaFile(id).existsSync()) _personaFile(id).deleteSync();
  }

  // ── chat history (active / live chat) ────────────────────────────────────────

  List<ChatMessage> loadChat(String charId) =>
      _readJsonList(_chatFile(charId))
          .map((e) => ChatMessage.fromJson(e))
          .toList();

  void saveChat(String charId, List<ChatMessage> messages) =>
      _writeJson(_chatFile(charId), messages.map((m) => m.toJson()).toList());

  void clearChat(String charId) {
    if (_chatFile(charId).existsSync()) _chatFile(charId).deleteSync();
  }

  // ── sessions (named chat history snapshots) ───────────────────────────────────

  /// Save current chat as a named session. Returns the session.
  ChatSession saveSession(String charId, String charName, List<ChatMessage> messages) {
    final id = '${charId}_${DateTime.now().millisecondsSinceEpoch}';
    final firstUserMsg = messages.firstWhere(
      (m) => m.isUser,
      orElse: () => ChatMessage(role: 'user', content: ''),
    );
    final title = firstUserMsg.content.isNotEmpty
        ? (firstUserMsg.content.length > 40
            ? '${firstUserMsg.content.substring(0, 40)}…'
            : firstUserMsg.content)
        : 'Chat ${DateTime.now().month}/${DateTime.now().day}';

    final session = ChatSession(
      id: id,
      charId: charId,
      title: title,
      createdAt: DateTime.now(),
      messages: messages,
    );
    _writeJson(_sessionFile(id), session.toJson());
    return session;
  }

  /// Load all sessions for a character, newest first.
  List<ChatSession> loadSessions(String charId) {
    final dir = Directory('${_base.path}/sessions');
    if (!dir.existsSync()) return [];
    final results = <ChatSession>[];
    for (final f in dir.listSync().whereType<File>()) {
      try {
        final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
        if (j['char_id'] == charId) {
          results.add(ChatSession.fromJson(j));
        }
      } catch (_) {}
    }
    results.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return results;
  }

  void deleteSession(String sessionId) {
    final f = _sessionFile(sessionId);
    if (f.existsSync()) f.deleteSync();
  }

  // ── memories ─────────────────────────────────────────────────────────────────

  List<String> loadMemory(String charId) =>
      _readJsonList(_memFile(charId)).map((e) => e.toString()).toList();

  void saveMemory(String charId, List<String> facts) =>
      _writeJson(_memFile(charId), facts);

  void addMemoryFact(String charId, String fact) {
    final facts = loadMemory(charId);
    if (!facts.contains(fact)) {
      facts.add(fact);
      if (facts.length > 60) facts.removeRange(0, facts.length - 60);
      saveMemory(charId, facts);
    }
  }

  void deleteMemoryFact(String charId, int index) {
    final facts = loadMemory(charId);
    if (index >= 0 && index < facts.length) {
      facts.removeAt(index);
      saveMemory(charId, facts);
    }
  }

  // ── roleplay story state ────────────────────────────────────────────────────

  StoryState loadStoryState(String charId) {
    final json = _readJson(_storyStateFile(charId));
    return StoryState.fromJson(json);
  }

  void saveStoryState(String charId, StoryState state) {
    final normalized = state.copyWith(
      keyEvents: state.keyEvents.where((e) => e.trim().isNotEmpty).toList().reversed.take(16).toList().reversed.toList(),
      openThreads: state.openThreads.where((e) => e.trim().isNotEmpty).toList().reversed.take(12).toList().reversed.toList(),
      updatedAt: DateTime.now(),
    );
    _writeJson(_storyStateFile(charId), normalized.toJson());
  }

  void clearStoryState(String charId) {
    final file = _storyStateFile(charId);
    if (file.existsSync()) file.deleteSync();
  }

}
