// login_screen.dart

import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../theme.dart';
import 'register_screen.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _pw = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;

  Future<void> _login() async {
    setState(() { _loading = true; _error = null; });
    final result = await AuthService.instance.login(password: _pw.text);
    if (!mounted) return;
    if (result.ok) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const HomeScreen()),
      );
    } else {
      setState(() { _error = result.error; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: AppBackground(child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 380),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 24),
                  const GradientText('CharChat',
                      style: TextStyle(fontSize: 38, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Text('Welcome back', style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: kMuted)),
                  const SizedBox(height: 40),
                  TextFormField(
                    controller: _pw,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                        onPressed: () => setState(() => _obscure = !_obscure),
                        color: kMuted,
                      ),
                    ),
                    onFieldSubmitted: (_) => _login(),
                    style: const TextStyle(color: kText),
                    autofocus: true,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: kDanger.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: kDanger.withOpacity(0.3)),
                      ),
                      child: Text(_error!, style: const TextStyle(color: kDanger, fontSize: 13)),
                    ),
                  ],
                  const SizedBox(height: 20),
                  GradientButton(
                    onPressed: _loading ? null : _login,
                    child: _loading
                        ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Unlock'),
                  ),
                  const SizedBox(height: 32),
                  const Divider(color: kBorder),
                  const SizedBox(height: 16),
                  Text(
                    'New device or first launch?',
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const RegisterScreen()),
                    ),
                    child: const Text('Set up account'),
                  ),
                ],
              ),
            ),
          ),
        ),
      )),
    );
  }
}
