// app_provider.dart — global state via ChangeNotifier

import 'package:flutter/foundation.dart';
import '../models/models.dart';
import '../services/storage_service.dart';
import '../services/ollama_service.dart';

class AppProvider extends ChangeNotifier {
  final _store = StorageService.instance;

  AppSettings _settings = const AppSettings();
  List<Character> _characters = [];
  List<Persona> _personas = [];
  Character? _activeChar;

  AppSettings get settings => _settings;
  List<Character> get characters => _characters;
  List<Persona> get personas => _personas;
  Character? get activeChar => _activeChar;
  ChatAppearance get appearance => _settings.appearance;

  Persona? get activePersona {
    final id = _settings.activePersonaId;
    if (id.isEmpty) return null;
    try {
      return _personas.firstWhere((p) => p.id == id);
    } catch (_) {
      return null;
    }
  }

  String get displayName {
    final p = activePersona;
    if (p != null && p.name.isNotEmpty) return p.name;
    return _settings.userName.isNotEmpty ? _settings.userName : 'You';
  }

  Future<void> init() async {
    await _store.init();
    _settings = _store.loadSettings();
    _characters = _store.loadCharacters();
    _personas = _store.loadPersonas();
    notifyListeners();
  }

  // ── characters ───────────────────────────────────────────────────────────────

  void reloadCharacters() {
    _characters = _store.loadCharacters();
    notifyListeners();
  }

  void saveCharacter(Character c) {
    _store.saveCharacter(c);
    reloadCharacters();
  }

  void deleteCharacter(String id) {
    _store.deleteCharacter(id);
    if (_activeChar?.id == id) _activeChar = null;
    reloadCharacters();
  }

  void setActiveChar(Character c) {
    _activeChar = c;
    notifyListeners();
  }

  // ── personas ─────────────────────────────────────────────────────────────────

  void reloadPersonas() {
    _personas = _store.loadPersonas();
    notifyListeners();
  }

  void savePersona(Persona p) {
    _store.savePersona(p);
    reloadPersonas();
  }

  void deletePersona(String id) {
    _store.deletePersona(id);
    if (_settings.activePersonaId == id) {
      _settings = _settings.copyWith(activePersonaId: '');
      _store.saveSettings(_settings);
    }
    reloadPersonas();
  }

  void setActivePersona(String id) {
    _settings = _settings.copyWith(activePersonaId: id);
    _store.saveSettings(_settings);
    notifyListeners();
  }

  void deactivatePersona() => setActivePersona('');

  // ── appearance ────────────────────────────────────────────────────────────────

  void saveAppearance(ChatAppearance a) {
    _settings = _settings.copyWith(appearance: a);
    _store.saveSettings(_settings);
    notifyListeners();
  }

  // ── settings ─────────────────────────────────────────────────────────────────

  void saveSettings(AppSettings s) {
    _settings = s.copyWith(activePersonaId: _settings.activePersonaId);
    _store.saveSettings(_settings);
    notifyListeners();
  }
}
