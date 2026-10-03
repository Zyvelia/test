// models.dart — all data models for CharChat

import 'dart:convert';

// ── Character ─────────────────────────────────────────────────────────────────

class Character {
  final String id;
  final String name;
  final String category;
  final String avatar;
  final String personality;
  final String scenario;
  final String greeting;
  final String examples;
  final List<String> tags;
  final String visibility;
  final bool nsfw;
  final String nsfwDescription;

  Character({
    required this.id,
    required this.name,
    this.category = 'Original',
    this.avatar = '',
    this.personality = '',
    this.scenario = '',
    this.greeting = '',
    this.examples = '',
    this.tags = const [],
    this.visibility = 'Private',
    this.nsfw = false,
    this.nsfwDescription = '',
  });

  factory Character.fromJson(Map<String, dynamic> j) => Character(
        id: j['id'] ?? '',
        name: j['name'] ?? 'Unnamed',
        category: j['category'] ?? 'Original',
        avatar: j['avatar'] ?? '',
        personality: j['personality'] ?? '',
        scenario: j['scenario'] ?? '',
        greeting: j['greeting'] ?? '',
        examples: j['examples'] ?? '',
        tags: List<String>.from(j['tags'] ?? []),
        visibility: j['visibility'] ?? 'Private',
        nsfw: j['nsfw'] ?? false,
        nsfwDescription: j['nsfw_description'] ?? '',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'category': category,
        'avatar': avatar,
        'personality': personality,
        'scenario': scenario,
        'greeting': greeting,
        'examples': examples,
        'tags': tags,
        'visibility': visibility,
        'nsfw': nsfw,
        'nsfw_description': nsfwDescription,
      };

  Character copyWith({
    String? id,
    String? name,
    String? category,
    String? avatar,
    String? personality,
    String? scenario,
    String? greeting,
    String? examples,
    List<String>? tags,
    String? visibility,
    bool? nsfw,
    String? nsfwDescription,
  }) =>
      Character(
        id: id ?? this.id,
        name: name ?? this.name,
        category: category ?? this.category,
        avatar: avatar ?? this.avatar,
        personality: personality ?? this.personality,
        scenario: scenario ?? this.scenario,
        greeting: greeting ?? this.greeting,
        examples: examples ?? this.examples,
        tags: tags ?? this.tags,
        visibility: visibility ?? this.visibility,
        nsfw: nsfw ?? this.nsfw,
        nsfwDescription: nsfwDescription ?? this.nsfwDescription,
      );
}

// ── Persona ───────────────────────────────────────────────────────────────────

class Persona {
  final String id;
  final String name;
  final String avatar;
  final String appearance;
  final String personality;
  final String backstory;
  final List<String> traits;

  Persona({
    required this.id,
    required this.name,
    this.avatar = '',
    this.appearance = '',
    this.personality = '',
    this.backstory = '',
    this.traits = const [],
  });

  factory Persona.fromJson(Map<String, dynamic> j) => Persona(
        id: j['id'] ?? '',
        name: j['name'] ?? 'Unnamed',
        avatar: j['avatar'] ?? '',
        appearance: j['appearance'] ?? '',
        personality: j['personality'] ?? '',
        backstory: j['backstory'] ?? '',
        traits: List<String>.from(j['traits'] ?? []),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'avatar': avatar,
        'appearance': appearance,
        'personality': personality,
        'backstory': backstory,
        'traits': traits,
      };

  Persona copyWith({
    String? id,
    String? name,
    String? avatar,
    String? appearance,
    String? personality,
    String? backstory,
    List<String>? traits,
  }) =>
      Persona(
        id: id ?? this.id,
        name: name ?? this.name,
        avatar: avatar ?? this.avatar,
        appearance: appearance ?? this.appearance,
        personality: personality ?? this.personality,
        backstory: backstory ?? this.backstory,
        traits: traits ?? this.traits,
      );
}

// ── ChatMessage ───────────────────────────────────────────────────────────────

class ChatMessage {
  final String role; // 'user' | 'assistant' | 'system'
  final String content;

  ChatMessage({required this.role, required this.content});

  factory ChatMessage.fromJson(Map<String, dynamic> j) =>
      ChatMessage(role: j['role'] ?? 'user', content: j['content'] ?? '');

  Map<String, dynamic> toJson() => {'role': role, 'content': content};

  bool get isUser => role == 'user';
  bool get isAssistant => role == 'assistant';
}

// ── ChatSession — a named snapshot of a conversation ─────────────────────────

class ChatSession {
  final String id;
  final String charId;
  final String title;
  final DateTime createdAt;
  final List<ChatMessage> messages;

  ChatSession({
    required this.id,
    required this.charId,
    required this.title,
    required this.createdAt,
    required this.messages,
  });

  factory ChatSession.fromJson(Map<String, dynamic> j) => ChatSession(
        id: j['id'] ?? '',
        charId: j['char_id'] ?? '',
        title: j['title'] ?? 'Chat',
        createdAt: DateTime.tryParse(j['created_at'] ?? '') ?? DateTime.now(),
        messages: (j['messages'] as List<dynamic>? ?? [])
            .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'char_id': charId,
        'title': title,
        'created_at': createdAt.toIso8601String(),
        'messages': messages.map((m) => m.toJson()).toList(),
      };
}

// ── ChatAppearance ────────────────────────────────────────────────────────────

enum BubbleStyle { rounded, sharp, minimal }
enum BackgroundPreset { default_, midnight, dusk, forest, ocean, rose }

class ChatAppearance {
  final BubbleStyle bubbleStyle;
  final BackgroundPreset background;
  final int userBubbleColorIndex;  // index into palette
  final int charBubbleColorIndex;
  final double fontSize;

  const ChatAppearance({
    this.bubbleStyle = BubbleStyle.rounded,
    this.background = BackgroundPreset.default_,
    this.userBubbleColorIndex = 0,
    this.charBubbleColorIndex = 1,
    this.fontSize = 15.0,
  });

  factory ChatAppearance.fromJson(Map<String, dynamic> j) => ChatAppearance(
        bubbleStyle: BubbleStyle.values.firstWhere(
          (e) => e.name == (j['bubble_style'] ?? 'rounded'),
          orElse: () => BubbleStyle.rounded,
        ),
        background: BackgroundPreset.values.firstWhere(
          (e) => e.name == (j['background'] ?? 'default_'),
          orElse: () => BackgroundPreset.default_,
        ),
        userBubbleColorIndex: j['user_color'] ?? 0,
        charBubbleColorIndex: j['char_color'] ?? 1,
        fontSize: (j['font_size'] ?? 15.0).toDouble(),
      );

  Map<String, dynamic> toJson() => {
        'bubble_style': bubbleStyle.name,
        'background': background.name,
        'user_color': userBubbleColorIndex,
        'char_color': charBubbleColorIndex,
        'font_size': fontSize,
      };

  ChatAppearance copyWith({
    BubbleStyle? bubbleStyle,
    BackgroundPreset? background,
    int? userBubbleColorIndex,
    int? charBubbleColorIndex,
    double? fontSize,
  }) =>
      ChatAppearance(
        bubbleStyle: bubbleStyle ?? this.bubbleStyle,
        background: background ?? this.background,
        userBubbleColorIndex: userBubbleColorIndex ?? this.userBubbleColorIndex,
        charBubbleColorIndex: charBubbleColorIndex ?? this.charBubbleColorIndex,
        fontSize: fontSize ?? this.fontSize,
      );
}

// ── AppSettings ───────────────────────────────────────────────────────────────

class AppSettings {
  final String ollamaUrl;
  final String model;
  final String userName;
  final String userPersona;
  final String activePersonaId;
  final int contextWindow;
  final String responseStyle; // concise | balanced | verbose
  final ChatAppearance appearance;

  const AppSettings({
    this.ollamaUrl = 'http://192.168.1.100:11434',
    this.model = 'dolphin-mistral',
    this.userName = 'You',
    this.userPersona = '',
    this.activePersonaId = '',
    this.contextWindow = 40,
    this.responseStyle = 'balanced',
    this.appearance = const ChatAppearance(),
  });

  factory AppSettings.fromJson(Map<String, dynamic> j) => AppSettings(
        ollamaUrl: j['ollama_url'] ?? 'http://192.168.1.100:11434',
        model: j['model'] ?? 'dolphin-mistral',
        userName: j['user_name'] ?? 'You',
        userPersona: j['user_persona'] ?? '',
        activePersonaId: j['active_persona_id'] ?? '',
        contextWindow: j['context_window'] ?? 40,
        responseStyle: j['response_style'] ?? 'balanced',
        appearance: j['appearance'] != null
            ? ChatAppearance.fromJson(j['appearance'] as Map<String, dynamic>)
            : const ChatAppearance(),
      );

  Map<String, dynamic> toJson() => {
        'ollama_url': ollamaUrl,
        'model': model,
        'user_name': userName,
        'user_persona': userPersona,
        'active_persona_id': activePersonaId,
        'context_window': contextWindow,
        'response_style': responseStyle,
        'appearance': appearance.toJson(),
      };

  AppSettings copyWith({
    String? ollamaUrl,
    String? model,
    String? userName,
    String? userPersona,
    String? activePersonaId,
    int? contextWindow,
    String? responseStyle,
    ChatAppearance? appearance,
  }) =>
      AppSettings(
        ollamaUrl: ollamaUrl ?? this.ollamaUrl,
        model: model ?? this.model,
        userName: userName ?? this.userName,
        userPersona: userPersona ?? this.userPersona,
        activePersonaId: activePersonaId ?? this.activePersonaId,
        contextWindow: contextWindow ?? this.contextWindow,
        responseStyle: responseStyle ?? this.responseStyle,
        appearance: appearance ?? this.appearance,
      );
}
