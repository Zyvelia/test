"""Shared permission checks, independent of Discord network calls."""
def safe_self_role(role, bot_member):
    dangerous = ('administrator', 'manage_guild', 'manage_roles', 'manage_channels',
                 'ban_members', 'kick_members', 'moderate_members', 'manage_webhooks',
                 'manage_messages', 'mention_everyone', 'view_audit_log', 'manage_threads',
                 'manage_events', 'manage_expressions', 'manage_nicknames',
                 'mute_members', 'deafen_members', 'move_members')
    return (not role.is_default() and not role.managed
            and role < bot_member.top_role
            and not any(getattr(role.permissions, name, False) for name in dangerous))


def may_moderate(actor, target, bot_member, owner_id):
    if target.id in (owner_id, actor.id, bot_member.id):
        return False
    if target.top_role >= bot_member.top_role:
        return False
    return actor.id == owner_id or actor.top_role > target.top_role


def may_close(user, ticket, staff_id):
    return (user.id == ticket['user'] or user.guild_permissions.manage_channels
            or any(role.id == staff_id for role in user.roles))
