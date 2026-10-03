// auth_service.dart — local auth: salted SHA-256, flutter_secure_storage

import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  static AuthService? _instance;
  static AuthService get instance => _instance ??= AuthService._();
  AuthService._();

  static const _storage = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  static const _keyUsername = 'cc_username';
  static const _keyEmail = 'cc_email';
  static const _keyHash = 'cc_pw_hash';
  static const _keySalt = 'cc_pw_salt';
  static const _keyLoggedIn = 'cc_session';
  static const _keyFailures = 'cc_failures';
  static const _keyLockUntil = 'cc_lock_until';

  static const _maxFailures = 5;
  static const _lockSeconds = 300; // 5 min lockout

  // ── hashing ──────────────────────────────────────────────────────────────────

  String _hash(String password, String salt) {
    // 10,000 stretching rounds with SHA-256
    var bytes = utf8.encode(password + salt);
    for (int i = 0; i < 10000; i++) {
      bytes = Uint8List.fromList(sha256.convert(bytes).bytes);
    }
    return base64Encode(bytes);
  }

  String _newSalt() {
    final now = DateTime.now().microsecondsSinceEpoch.toString();
    return base64Encode(sha256.convert(utf8.encode(now)).bytes).substring(0, 32);
  }

  // ── registration ─────────────────────────────────────────────────────────────

  Future<bool> isRegistered() async {
    final h = await _storage.read(key: _keyHash);
    return h != null && h.isNotEmpty;
  }

  /// Returns null on success, error string on failure
  Future<String?> register({
    required String username,
    required String email,
    required String password,
  }) async {
    if (username.trim().length < 2) return 'Username must be at least 2 characters.';
    if (!RegExp(r'^[^@]+@[^@]+\.[^@]+$').hasMatch(email.trim())) {
      return 'Enter a valid email.';
    }
    if (password.length < 6) return 'Password must be at least 6 characters.';

    final salt = _newSalt();
    final hash = _hash(password, salt);
    await _storage.write(key: _keyUsername, value: username.trim());
    await _storage.write(key: _keyEmail, value: email.trim().toLowerCase());
    await _storage.write(key: _keySalt, value: salt);
    await _storage.write(key: _keyHash, value: hash);
    await _storage.write(key: _keyLoggedIn, value: '1');
    return null;
  }

  // ── login ────────────────────────────────────────────────────────────────────

  Future<({bool ok, String? error})> login({required String password}) async {
    // check lockout
    final lockStr = await _storage.read(key: _keyLockUntil);
    if (lockStr != null) {
      final lockUntil = DateTime.fromMillisecondsSinceEpoch(int.parse(lockStr));
      if (DateTime.now().isBefore(lockUntil)) {
        final secs = lockUntil.difference(DateTime.now()).inSeconds;
        return (ok: false, error: 'Too many attempts. Wait ${secs}s.');
      } else {
        await _storage.delete(key: _keyLockUntil);
        await _storage.write(key: _keyFailures, value: '0');
      }
    }

    final salt = await _storage.read(key: _keySalt) ?? '';
    final stored = await _storage.read(key: _keyHash) ?? '';
    final attempt = _hash(password, salt);

    if (attempt == stored) {
      await _storage.write(key: _keyFailures, value: '0');
      await _storage.write(key: _keyLoggedIn, value: '1');
      return (ok: true, error: null);
    }

    // increment failures
    final failStr = await _storage.read(key: _keyFailures) ?? '0';
    final fails = int.parse(failStr) + 1;
    await _storage.write(key: _keyFailures, value: fails.toString());

    if (fails >= _maxFailures) {
      final lockUntil = DateTime.now().add(const Duration(seconds: _lockSeconds));
      await _storage.write(
          key: _keyLockUntil,
          value: lockUntil.millisecondsSinceEpoch.toString());
      return (ok: false, error: 'Too many attempts. Locked for ${_lockSeconds ~/ 60} minutes.');
    }

    return (ok: false, error: 'Incorrect password. ${_maxFailures - fails} attempts left.');
  }

  Future<bool> isLoggedIn() async {
    final v = await _storage.read(key: _keyLoggedIn);
    return v == '1';
  }

  Future<void> logout() async {
    await _storage.write(key: _keyLoggedIn, value: '0');
  }

  Future<String?> getUsername() => _storage.read(key: _keyUsername);
  Future<String?> getEmail() => _storage.read(key: _keyEmail);

  Future<String?> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    final r = await login(password: oldPassword);
    if (!r.ok) return 'Current password incorrect.';
    if (newPassword.length < 6) return 'New password too short.';
    final salt = _newSalt();
    final hash = _hash(newPassword, salt);
    await _storage.write(key: _keySalt, value: salt);
    await _storage.write(key: _keyHash, value: hash);
    return null;
  }
}
