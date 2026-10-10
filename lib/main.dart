// main.dart — CharChat Flutter entry point

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'providers/app_provider.dart';
import 'services/auth_service.dart';
import 'services/storage_service.dart';
import 'screens/login_screen.dart';
import 'screens/register_screen.dart';
import 'screens/home_screen.dart';
import 'theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarBrightness: Brightness.dark,
    statusBarIconBrightness: Brightness.light,
  ));
  await StorageService.instance.init();
  runApp(const CharChatApp());
}

class CharChatApp extends StatelessWidget {
  const CharChatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppProvider()..init(),
      child: MaterialApp(
        title: 'CharChat',
        theme: buildTheme(),
        debugShowCheckedModeBanner: false,
        home: const _Splash(),
      ),
    );
  }
}

// decides login vs register vs home
class _Splash extends StatefulWidget {
  const _Splash();

  @override
  State<_Splash> createState() => _SplashState();
}

class _SplashState extends State<_Splash> {
  @override
  void initState() {
    super.initState();
    _route();
  }

  Future<void> _route() async {
    final registered = await AuthService.instance.isRegistered();
    final loggedIn   = registered && await AuthService.instance.isLoggedIn();

    if (!mounted) return;

    if (!registered) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const RegisterScreen()),
      );
    } else if (loggedIn) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const HomeScreen()),
      );
    } else {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: const AppBackground(child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            GradientText('CharChat',
                style: TextStyle(fontSize: 36, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
            SizedBox(height: 24),
            CircularProgressIndicator(color: kPrimary),
          ],
        ),
      )),
    );
  }
}
