// theme.dart — CharChat dark theme

import 'dart:io';
import 'package:flutter/material.dart';

const kBg = Color(0xFF0B0B12);
const kSurface = Color(0xFF12121B);
const kCard = Color(0xFF181824);
const kBorder = Color(0xFF2A2A3C);
const kPrimary = Color(0xFF8B7CF6);
const kPrimary2 = Color(0xFFEC6FB0); // gradient partner
const kDanger = Color(0xFFFF6B7A);
const kMuted = Color(0xFF8E8EA8);
const kText = Color(0xFFF2F2F8);
const kTextSoft = Color(0xFFCFCFE0);
const kAction = Color(0xFFA9A3D6); // *action* text color
const kBubbleUser = Color(0xFF3B2F7A);
const kBubbleChar = Color(0xFF1B1B29);
const kGreen = Color(0xFF4ADE80);

const kCyan = Color(0xFF38BDF8);
const kAmber = Color(0xFFFBBF24);
const kTeal = Color(0xFF2DD4BF);
const kRose = Color(0xFFFB7185);
const kOrange = Color(0xFFFB923C);
const kBlue = Color(0xFF60A5FA);

const kGradient = LinearGradient(
  colors: [kPrimary, kPrimary2],
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
);

ThemeData buildTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: kBg,
    colorScheme: const ColorScheme.dark(
      primary: kPrimary,
      surface: kSurface,
      onSurface: kText,
      error: kDanger,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: kText,
      elevation: 0,
      surfaceTintColor: Colors.transparent,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: kSurface,
      indicatorColor: kPrimary.withOpacity(0.22),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(color: kMuted, fontSize: 11),
      ),
    ),
    cardTheme: const CardThemeData(
      color: kCard,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(16)),
        side: BorderSide(color: kBorder, width: 1),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kSurface,
      hintStyle: const TextStyle(color: kMuted),
      labelStyle: const TextStyle(color: kMuted),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: kBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: kPrimary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: kDanger),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: kDanger, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: kPrimary,
        foregroundColor: Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: kText,
        side: const BorderSide(color: kBorder),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: kPrimary,
      ),
    ),
    dividerColor: kBorder,
    textTheme: const TextTheme(
      headlineMedium: TextStyle(color: kText, fontWeight: FontWeight.w700, fontSize: 22),
      titleLarge: TextStyle(color: kText, fontWeight: FontWeight.w600, fontSize: 17),
      titleMedium: TextStyle(color: kText, fontWeight: FontWeight.w500, fontSize: 15),
      bodyLarge: TextStyle(color: kTextSoft, fontSize: 15),
      bodyMedium: TextStyle(color: kTextSoft, fontSize: 14),
      bodySmall: TextStyle(color: kMuted, fontSize: 12),
      labelLarge: TextStyle(color: kText, fontWeight: FontWeight.w600, fontSize: 14),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: kCard,
      labelStyle: const TextStyle(color: kMuted, fontSize: 12),
      side: const BorderSide(color: kBorder),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: kCard,
      behavior: SnackBarBehavior.floating,
      contentTextStyle: TextStyle(color: kText),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: kSurface,
      selectedItemColor: kPrimary,
      unselectedItemColor: kMuted,
    ),
    iconTheme: const IconThemeData(color: kMuted),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: kPrimary),
    dialogTheme: DialogThemeData(
      backgroundColor: kCard,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      titleTextStyle: TextStyle(color: kText, fontSize: 17, fontWeight: FontWeight.w600),
      contentTextStyle: TextStyle(color: kTextSoft, fontSize: 14),
    ),
  );
}


// ── shared widgets ────────────────────────────────────────────────────────────

/// Round/rounded avatar: image if available, otherwise gradient initial.
class CharAvatar extends StatelessWidget {
  final String name;
  final String path;
  final double size;
  final double radius;
  final String seed;
  const CharAvatar({super.key, required this.name, this.path = '', this.size = 48, this.radius = 16, this.seed = ''});

  @override
  Widget build(BuildContext context) {
    final r = BorderRadius.circular(radius);
    if (path.isNotEmpty && File(path).existsSync()) {
      return ClipRRect(
        borderRadius: r,
        child: Image.file(File(path), width: size, height: size, fit: BoxFit.cover),
      );
    }
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: gradientFor(seed.isNotEmpty ? seed : name),
        borderRadius: r,
        boxShadow: [BoxShadow(color: accentFor(seed.isNotEmpty ? seed : name).first.withOpacity(0.35), blurRadius: 10, offset: const Offset(0, 3))],
      ),
      alignment: Alignment.center,
      child: Text(
        name.isNotEmpty ? name[0].toUpperCase() : '?',
        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: size * 0.42),
      ),
    );
  }
}

class GradientText extends StatelessWidget {
  final String text;
  final TextStyle style;
  const GradientText(this.text, {super.key, required this.style});

  @override
  Widget build(BuildContext context) => ShaderMask(
        shaderCallback: (r) => kGradient.createShader(r),
        child: Text(text, style: style.copyWith(color: Colors.white)),
      );
}


// ── per-character accent colours ──────────────────────────────────────────────

const _accents = <List<Color>>[
  [Color(0xFF8B7CF6), Color(0xFFEC6FB0)], // violet → pink
  [Color(0xFF38BDF8), Color(0xFF6366F1)], // sky → indigo
  [Color(0xFF2DD4BF), Color(0xFF38BDF8)], // teal → sky
  [Color(0xFFFB923C), Color(0xFFF43F5E)], // orange → rose
  [Color(0xFFFBBF24), Color(0xFFFB7185)], // amber → rose
  [Color(0xFF34D399), Color(0xFF22D3EE)], // green → cyan
  [Color(0xFFA78BFA), Color(0xFF38BDF8)], // lavender → sky
  [Color(0xFFF472B6), Color(0xFFFB923C)], // pink → orange
];

List<Color> accentFor(String key) {
  var h = 0;
  for (final c in key.codeUnits) {
    h = (h * 31 + c) & 0x7fffffff;
  }
  return _accents[h % _accents.length];
}

LinearGradient gradientFor(String key) {
  final a = accentFor(key);
  return LinearGradient(colors: a, begin: Alignment.topLeft, end: Alignment.bottomRight);
}

Color categoryColor(String cat) {
  switch (cat) {
    case 'Anime':         return kPrimary2;
    case 'Fantasy':       return kPrimary;
    case 'Games':         return kGreen;
    case 'Sci-Fi':        return kCyan;
    case 'Historical':    return kAmber;
    case 'Roleplay':      return kRose;
    case 'Horror':        return kDanger;
    case 'Slice of Life': return kTeal;
    case 'Original':      return kBlue;
    default:              return kOrange;
  }
}

// ── app background: soft coloured glow behind everything ─────────────────────

class AppBackground extends StatelessWidget {
  final Widget child;
  const AppBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) => Stack(
        children: [
          Positioned.fill(child: Container(color: kBg)),
          Positioned(
            top: -120, left: -80,
            child: _glow(kPrimary, 340),
          ),
          Positioned(
            top: 120, right: -140,
            child: _glow(kPrimary2, 300),
          ),
          Positioned(
            bottom: -140, left: -60,
            child: _glow(kCyan, 300),
          ),
          Positioned.fill(child: child),
        ],
      );

  Widget _glow(Color c, double size) => IgnorePointer(
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [c.withOpacity(0.20), c.withOpacity(0.0)],
            ),
          ),
        ),
      );
}

class GradientButton extends StatelessWidget {
  final VoidCallback? onPressed;
  final Widget child;
  final Gradient gradient;
  const GradientButton({
    super.key,
    required this.onPressed,
    required this.child,
    this.gradient = kGradient,
  });

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Opacity(
      opacity: enabled ? 1 : 0.55,
      child: Container(
        decoration: BoxDecoration(
          gradient: gradient,
          borderRadius: BorderRadius.circular(14),
          boxShadow: [BoxShadow(color: kPrimary.withOpacity(0.35), blurRadius: 14, offset: const Offset(0, 5))],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: onPressed,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
              child: DefaultTextStyle(
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15),
                child: IconTheme(
                  data: const IconThemeData(color: Colors.white),
                  child: Center(child: child),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
