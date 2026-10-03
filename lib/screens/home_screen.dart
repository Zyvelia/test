// home_screen.dart — bottom nav shell

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_provider.dart';
import '../theme.dart';
import 'library_screen.dart';
import 'chat_screen.dart';
import 'personas_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tab = 0;

  final _tabs = const [
    NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome, color: kPrimary), label: 'Characters'),
    NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_bubble, color: kPrimary2), label: 'Chat'),
    NavigationDestination(icon: Icon(Icons.face_outlined), selectedIcon: Icon(Icons.face, color: kCyan), label: 'Personas'),
    NavigationDestination(icon: Icon(Icons.tune_outlined), selectedIcon: Icon(Icons.tune, color: kAmber), label: 'Settings'),
  ];

  void goToChat() => setState(() => _tab = 1);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: AppBackground(
        child: SafeArea(
          bottom: false,
          child: IndexedStack(
            index: _tab,
            children: [
              LibraryScreen(onOpenChar: (_) => goToChat()),
              const ChatScreen(),
              const PersonasScreen(),
              const SettingsScreen(),
            ],
          ),
        ),
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: kBorder, width: 0.5)),
          color: kSurface,
        ),
        child: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: _tabs,
          backgroundColor: kBg,
          surfaceTintColor: Colors.transparent,
          indicatorColor: kPrimary.withOpacity(0.18),
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          height: 64,
        ),
      ),
    );
  }
}
