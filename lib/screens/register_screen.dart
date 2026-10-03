// register_screen.dart

import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../theme.dart';
import 'home_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _pw = TextEditingController();
  final _pw2 = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;

  Future<void> _register() async {
    if (_pw.text != _pw2.text) {
      setState(() => _error = 'Passwords do not match.');
      return;
    }
    setState(() { _loading = true; _error = null; });
    final err = await AuthService.instance.register(
      username: _username.text,
      email: _email.text,
      password: _pw.text,
    );
    if (!mounted) return;
    if (err == null) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const HomeScreen()),
      );
    } else {
      setState(() { _error = err; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        title: const Text('Create account'),
        backgroundColor: kBg,
      ),
      body: AppBackground(child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 380),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const GradientText('CharChat',
                      style: TextStyle(fontSize: 38, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 6),
                  Text(
                    'Your credentials are stored on-device only.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _username,
                    decoration: const InputDecoration(labelText: 'Username'),
                    style: const TextStyle(color: kText),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email'),
                    style: const TextStyle(color: kText),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _pw,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      helperText: 'Min 6 characters',
                      helperStyle: const TextStyle(color: kMuted),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined, color: kMuted),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    style: const TextStyle(color: kText),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _pw2,
                    obscureText: _obscure,
                    decoration: const InputDecoration(labelText: 'Confirm password'),
                    onFieldSubmitted: (_) => _register(),
                    style: const TextStyle(color: kText),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 14),
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
                  const SizedBox(height: 24),
                  GradientButton(
                    onPressed: _loading ? null : _register,
                    child: _loading
                        ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Create account'),
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
