"""Local UI catalogs. User-written content is never sent to a translation service."""
from contextvars import ContextVar
import html
import re
import string
from discord import app_commands

UI_LANGUAGE=ContextVar('vivi_ui_language',default='en')
# English is the canonical/fallback text. Values are Spanish and French.
CATALOG={
'Welcome, {name}!':('¡Bienvenido, {name}!','Bienvenue, {name} !'),
'Please read the rules and choose your roles.':('Lee las reglas y elige tus roles.','Lisez les règles et choisissez vos rôles.'),
'Check whether the bot is online.':('Comprueba si el bot está conectado.','Vérifiez si le bot est connecté.'),
'See setup, member, and moderator commands.':('Consulta los comandos de configuración, miembros y moderación.','Consultez les commandes de configuration, membres et modération.'),
'Server features and configuration':('Funciones y configuración del servidor','Fonctionnalités et configuration du serveur'),
'Community activities, roles, polls, and support':('Actividades, roles, encuestas y soporte','Activités, rôles, sondages et support'),
'Trivia, word games, and multiplayer games':('Preguntas, palabras y juegos multijugador','Quiz, jeux de mots et jeux multijoueurs'),
'Profiles, achievements, levels, and cosmetic shop':('Perfiles, logros, niveles y tienda cosmética','Profils, succès, niveaux et boutique cosmétique'),
'Uploaded-audio queue and playback':('Cola y reproducción de audio','File et lecture audio'),
'Custom read-only command shortcuts':('Atajos de comandos informativos','Raccourcis de commandes informatives'),
'Server Dashboard':('Panel del servidor','Tableau de bord du serveur'),
'Feature switches':('Funciones','Fonctionnalités'),
'Server channels and support staff':('Canales y equipo de soporte','Salons et équipe de support'),
'Welcome, moderation, AI channels and other settings':('Bienvenida, moderación, IA y otros ajustes','Accueil, modération, IA et autres paramètres'),
'FAQ manager':('Preguntas frecuentes','Questions fréquentes'),
'Ticket categories and open tickets':('Categorías y tickets abiertos','Catégories et tickets ouverts'),
'Twitch, YouTube and GitHub notifications':('Notificaciones de Twitch, YouTube y GitHub','Notifications Twitch, YouTube et GitHub'),
'Backup and restore':('Copias de seguridad y restauración','Sauvegarde et restauration'),
'Live permission and provider checks':('Comprobación de permisos y proveedores','Vérification des permissions et fournisseurs'),
'Health dashboard':('Estado de Vivi','État de Vivi'),
'Configuration history':('Historial de configuración','Historique de configuration'),
'Dashboard previews':('Vistas previas','Aperçus'),
'Scheduled backups':('Copias programadas','Sauvegardes planifiées'),
'Enable':('Activar','Activer'),'Disable':('Desactivar','Désactiver'),
'On':('Activado','Activé'),'Off':('Desactivado','Désactivé'),
'Save setting':('Guardar ajuste','Enregistrer le paramètre'),
'Save server setup':('Guardar configuración del servidor','Enregistrer la configuration du serveur'),
'Remove':('Eliminar','Supprimer'),'Sign out':('Cerrar sesión','Se déconnecter'),
'Add or update FAQ':('Añadir o actualizar respuesta','Ajouter ou modifier une réponse'),
'Add or update category':('Añadir o actualizar categoría','Ajouter ou modifier une catégorie'),
'Remove category option':('Eliminar categoría','Supprimer la catégorie'),
'Add subscription':('Añadir suscripción','Ajouter un abonnement'),
'Restore configuration':('Restaurar configuración','Restaurer la configuration'),
'Preview welcome card':('Ver tarjeta de bienvenida','Aperçu de la carte de bienvenue'),
'Preview announcement':('Ver anuncio','Aperçu de l’annonce'),
'View revision':('Ver revisión','Voir la révision'),
'Roll back to this configuration':('Restaurar esta configuración','Restaurer cette configuration'),
'Download':('Descargar','Télécharger'),
'Test provider metadata (no Discord post)':('Probar proveedor (sin publicar en Discord)','Tester le fournisseur (sans publication Discord)'),
'Run checks without posting Discord messages':('Comprobar sin publicar en Discord','Vérifier sans publier sur Discord'),
'welcome text':('texto de bienvenida','texte de bienvenue'),'welcome color':('color de bienvenida','couleur de bienvenue'),
'goodbye text':('texto de despedida','texte de départ'),'goodbye channel':('canal de despedida','salon de départ'),
'autorole':('rol automático','rôle automatique'),'rules role':('rol de aceptación de reglas','rôle d’acceptation des règles'),
'rules text':('reglas','règles'),'blocked words':('palabras bloqueadas','mots bloqués'),
'blocked domains':('dominios bloqueados','domaines bloqués'),'spam limit':('límite de spam','limite de spam'),
'dm explanations':('explicaciones por mensaje privado','explications par message privé'),
'birthday channel':('canal de cumpleaños','salon des anniversaires'),'daily channel':('canal diario','salon quotidien'),
'daily hour':('hora diaria','heure quotidienne'),'timezone':('zona horaria','fuseau horaire'),
'ai channels':('canales de IA','salons IA'),'ai limit':('límite de IA','limite IA'),
'mention limit':('límite de menciones','limite de mentions'),'raid limit':('límite de entradas','seuil d’arrivées'),
'raid window':('intervalo de detección','fenêtre de détection'),'raid action':('acción ante ataques','action anti-raid'),
'raid channel':('canal de protección','salon de protection'),'raid lock minutes':('minutos de bloqueo','minutes de verrouillage'),
'warning count':('cantidad de advertencias','nombre d’avertissements'),
'warning timeout minutes':('minutos de silencio','minutes d’exclusion temporaire'),
'warning window days':('días del historial de advertencias','jours d’historique des avertissements'),
'voice lobby':('sala de creación de voz','salon de création vocale'),
'voice category':('categoría de voz','catégorie vocale'),'voice user limit':('límite de usuarios de voz','limite d’utilisateurs vocaux'),
'language':('idioma','langue'),'backup hours':('intervalo de copia en horas','intervalle de sauvegarde en heures'),
'backup keep':('copias conservadas','sauvegardes conservées'),
'You are now AFK: {reason}':('Ahora estás ausente: {reason}','Vous êtes maintenant absent : {reason}'),
'Welcome back, {name}. Your AFK status is cleared.':('Bienvenido de nuevo, {name}. Ya no estás ausente.','Bon retour, {name}. Votre statut d’absence est effacé.'),
'{name} is AFK: {reason}':('{name} está ausente: {reason}','{name} est absent : {reason}'),
'AFK status cleared.':('Estado de ausencia eliminado.','Statut d’absence effacé.'),
'Language saved.':('Idioma guardado.','Langue enregistrée.'),
'This feature is disabled here.':('Esta función está desactivada aquí.','Cette fonctionnalité est désactivée ici.'),
'You do not have permission to use this command.':('No tienes permiso para usar este comando.','Vous n’avez pas la permission d’utiliser cette commande.'),
'No matching FAQ found.':('No se encontraron respuestas.','Aucune réponse correspondante.'),
'Configuration saved. Run /ticket_panel and /role_button where you want member buttons.':('Configuración guardada. Usa /ticket_panel y /role_button para publicar botones.','Configuration enregistrée. Utilisez /ticket_panel et /role_button pour publier les boutons.'),
'Ticket claimed.':('Ticket asignado.','Ticket pris en charge.'),'Ticket released.':('Ticket liberado.','Ticket libéré.'),
'Category updated; ticket privacy permissions were preserved.':('Categoría actualizada; se conservaron los permisos privados.','Catégorie modifiée ; permissions privées conservées.'),
'Only the ticket owner or support staff can close this ticket.':('Solo el autor o el equipo de soporte pueden cerrar este ticket.','Seul l’auteur ou le support peut fermer ce ticket.'),
'Ticket closed. Transcript saved on the host PC.':('Ticket cerrado. Transcripción guardada en el equipo anfitrión.','Ticket fermé. Transcription enregistrée sur l’ordinateur hôte.'),
'This role is unavailable or no longer safe to self-assign. Ask an admin.':('Este rol no está disponible para autoasignación. Consulta a un administrador.','Ce rôle n’est pas disponible en libre attribution. Contactez un administrateur.'),
'Your selections were saved. This menu replaces only the roles it lists.':('Selecciones guardadas. Este menú solo modifica los roles que muestra.','Choix enregistrés. Ce menu modifie uniquement les rôles affichés.'),
'Paused.':('En pausa.','En pause.'),'Resumed.':('Reproducción reanudada.','Lecture reprise.'),
'Skipped.':('Pista saltada.','Piste passée.'),'Disconnected.':('Desconectado.','Déconnecté.'),
'Playback stopped; queue cleared.':('Reproducción detenida; cola vacía.','Lecture arrêtée ; file vidée.'),
'No warnings recorded.':('No hay advertencias registradas.','Aucun avertissement enregistré.'),
'No public profiles yet.':('Aún no hay perfiles públicos.','Aucun profil public pour le moment.'),
'No pending requests.':('No hay solicitudes pendientes.','Aucune demande en attente.'),
'Unknown item. See /economy shop.':('Artículo desconocido. Consulta /economy shop.','Objet inconnu. Consultez /economy shop.'),
'You already own that item.':('Ya tienes ese artículo.','Vous possédez déjà cet objet.'),
'Stored AI conversation cleared.':('Conversación de IA guardada eliminada.','Conversation IA enregistrée effacée.'),
'AI memory disabled and erased.':('Memoria de IA desactivada y borrada.','Mémoire IA désactivée et effacée.'),
'You do not own that cosmetic.':('No tienes ese cosmético.','Vous ne possédez pas cet élément cosmétique.'),
'Room renamed.':('Sala renombrada.','Salon renommé.'),'Member limit updated.':('Límite de miembros actualizado.','Limite de membres modifiée.'),
'FAQ saved.':('Respuesta guardada.','Réponse enregistrée.'),'FAQ removed.':('Respuesta eliminada.','Réponse supprimée.'),
'Saved {name}.':('Se guardó {name}.','{name} enregistré.'),
'Priority: {value}.':('Prioridad: {value}.','Priorité : {value}.'),
'Volume: {percent}%.':('Volumen: {percent} %.','Volume : {percent} %.'),
'Added {name}.':('Se añadió {name}.','{name} ajouté.'),'Removed {name}.':('Se eliminó {name}.','{name} retiré.'),
'You already have a ticket: {channel}':('Ya tienes un ticket: {channel}','Vous avez déjà un ticket : {channel}'),
'Your private ticket is ready: {channel}':('Tu ticket privado está listo: {channel}','Votre ticket privé est prêt : {channel}'),
'Welcome {member} to {server}!':('¡Bienvenido {member} a {server}!','Bienvenue {member} sur {server} !'),
'Goodbye {member}.':('Adiós {member}.','Au revoir {member}.'),
'Online! Gateway latency: {ms} ms.':('¡En línea! Latencia: {ms} ms.','En ligne ! Latence : {ms} ms.'),
}

def tr(language,text,**values):
    translated=CATALOG.get(text)
    value=translated[0 if language=='es' else 1] if translated and language in {'es','fr'} else text
    return value.format(**values) if values else value

_PATTERNS=[]
for template in CATALOG:
    if '{' not in template: continue
    pattern=''; fields=[]
    for literal,name,spec,conversion in string.Formatter().parse(template):
        pattern+=re.escape(literal)
        if name: fields.append(name); pattern+='(.+?)'
    _PATTERNS.append((template,re.compile('^'+pattern+'$',re.S),fields))

def localize_message(language,text):
    if language not in {'es','fr'}: return text
    if text in CATALOG: return tr(language,text)
    for template,pattern,fields in _PATTERNS:
        match=pattern.match(text)
        if match: return tr(language,template,**dict(zip(fields,match.groups())))
    return text

def interaction_language(i):
    bot=getattr(i,'client',None); guild=getattr(i,'guild_id',None)
    if not bot or not hasattr(bot,'store') or not guild: return 'en'
    user=getattr(getattr(i,'user',None),'id',0)
    return bot.store.profile(guild,user).get('language') or bot.store.option(guild,'language','en')

def localize_html(language,content):
    if language=='en': return content
    def replace(match):
        start,text,end=match.groups(); plain=html.unescape(text.strip())
        translated=tr(language,plain)
        return start+html.escape(translated)+end if translated!=plain else match.group(0)
    return re.sub(r'(<(?:button|summary|label)\b[^>]*>)([^<>]*)(</(?:button|summary|label)>)',replace,content)

NAME_TRANSLATIONS={'help':('ayuda','aide'),'tools':('herramientas','outils'),'community':('comunidad','communaute'),
                   'games':('juegos','jeux'),'economy':('economia','economie'),'music':('musica','musique'),
                   'timezone':('zona_horaria','fuseau_horaire'),
                   'room':('sala','salon'),'notify':('avisos','annonces'),'afk':('ausente','absent'),'language':('idioma','langue')}

class ViviTranslator(app_commands.Translator):
    async def translate(self,string,locale,context):
        language=str(locale).split('-')[0]
        if language not in {'es','fr'}: return None
        names={app_commands.TranslationContextLocation.command_name,
               app_commands.TranslationContextLocation.group_name,
               app_commands.TranslationContextLocation.parameter_name}
        if context.location in names:
            values=NAME_TRANSLATIONS.get(string.message)
            if not values:return None
            name=values[0 if language=='es' else 1]
            # UI labels may contain spaces; Discord slash-command identifiers may not.
            if not isinstance(name,str) or not re.fullmatch(r'[\w-]{1,32}',name) or name!=name.lower():return None
            return name
        if string.message not in CATALOG: return None
        return tr(language,string.message)
