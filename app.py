import asyncio
import os
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import discord
from discord.ext import commands
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '0'))
if not TOKEN or not GUILD_ID:
    raise RuntimeError('Configure DISCORD_BOT_TOKEN et DISCORD_GUILD_ID dans .env')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)
ready = asyncio.Event()

@bot.event
async def on_ready():
    print(f'Bot connecté : {bot.user}')
    ready.set()

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(bot.start(TOKEN))
    try:
        yield
    finally:
        await bot.close()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title='Nebula Core', lifespan=lifespan)

async def guild():
    if not ready.is_set():
        raise HTTPException(503, 'Bot en cours de connexion')
    g = bot.get_guild(GUILD_ID)
    if not g:
        raise HTTPException(404, 'Serveur introuvable : vérifie DISCORD_GUILD_ID et invitation du bot')
    return g

@app.exception_handler(discord.Forbidden)
async def forbidden_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403, content={'detail': 'Permission Discord insuffisante ou rôle du bot trop bas'})

@app.exception_handler(discord.HTTPException)
async def discord_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={'detail': f'Erreur Discord : {exc.text}'})

# Historique local sans token ni contenu des messages.
LOG_PATH = Path(__file__).parent / 'data' / 'actions.jsonl'

def audit(action: str, details: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {'at': datetime.now(timezone.utc).isoformat(), 'action': action, 'details': details}
    with LOG_PATH.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + '\n')

@app.get('/api/history')
async def history():
    if not LOG_PATH.exists():
        return {'entries': []}
    lines = LOG_PATH.read_text(encoding='utf-8').splitlines()[-100:]
    return {'entries': [json.loads(line) for line in reversed(lines)]}

class CategoryTemplate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    text_channels: list[str] = Field(default_factory=list, max_length=20)
    voice_channels: list[str] = Field(default_factory=list, max_length=10)

@app.post('/api/categories/template')
async def create_category_template(payload: CategoryTemplate):
    g = await guild()
    texts = [x.strip() for x in payload.text_channels]
    voices = [x.strip() for x in payload.voice_channels]
    if not texts and not voices:
        raise HTTPException(400, 'Ajoute au moins un salon')
    if any(not x or len(x)>100 for x in texts+voices):
        raise HTTPException(400, 'Nom de salon invalide')
    cat = await g.create_category(payload.name.strip(), reason='Nebula Core V2.2 modèle')
    created = []
    try:
        for name in texts:
            c = await g.create_text_channel(name, category=cat, reason='Nebula Core V2.2 modèle')
            created.append({'id': str(c.id), 'name': c.name})
        for name in voices:
            c = await g.create_voice_channel(name, category=cat, reason='Nebula Core V2.2 modèle')
            created.append({'id': str(c.id), 'name': c.name})
    except discord.HTTPException as exc:
        audit('template_partial', {'category': cat.name, 'created': created, 'error': str(exc)})
        raise HTTPException(502, f'Création partielle : catégorie {cat.name}, {len(created)} salons créés. {exc}')
    audit('template_created', {'category': cat.name, 'channels': created})
    return {'category': {'id': str(cat.id), 'name': cat.name}, 'created': created}

@app.get('/')
async def index():
    return FileResponse(Path(__file__).parent / 'index.html')

@app.get('/api/health')
async def health():
    return {'connected': ready.is_set() and not bot.is_closed(), 'bot': str(bot.user) if bot.user else None}

@app.get('/api/state')
async def state():
    g = await guild()
    return {
        'name': g.name,
        'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color), 'position': r.position, 'managed': r.managed, 'hoist': r.hoist, 'mentionable': r.mentionable} for r in reversed(g.roles) if r != g.default_role],
        'categories': [{'id': str(c.id), 'name': c.name} for c in g.categories],
        'channels': [{'id': str(c.id), 'name': c.name, 'type': str(c.type), 'category_id': str(c.category_id) if c.category_id else None} for c in g.channels if not isinstance(c, discord.CategoryChannel)]
    }

class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = '#00d9ff'

@app.post('/api/roles')
async def create_role(payload: RoleCreate):
    g = await guild()
    try:
        color = discord.Color(int(payload.color.lstrip('#'), 16))
    except ValueError:
        raise HTTPException(400, 'Couleur hexadécimale invalide')
    role = await g.create_role(name=payload.name, color=color, reason='Nebula Core dashboard')
    return {'id': str(role.id), 'name': role.name}


class RolePreset(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default='#8eb5d3', pattern=r'^#[0-9a-fA-F]{6}$')
    hoist: bool = False

class RolePresetBatch(BaseModel):
    roles: list[RolePreset] = Field(min_length=1, max_length=15)

@app.post('/api/roles/presets')
async def create_role_presets(payload: RolePresetBatch):
    g = await guild()
    names = [r.name.strip() for r in payload.roles]
    if any(not n for n in names) or len({n.casefold() for n in names}) != len(names):
        raise HTTPException(400, 'Noms de rôles vides ou dupliqués dans la sélection')
    existing = {r.name.casefold() for r in g.roles}
    created, skipped = [], []
    for preset in payload.roles:
        name = preset.name.strip()
        if name.casefold() in existing:
            skipped.append(name)
            continue
        try:
            role = await g.create_role(name=name, color=discord.Color(int(preset.color[1:], 16)),
                                       hoist=preset.hoist, mentionable=False,
                                       permissions=discord.Permissions.none(), reason='Nebula Core V2.3 préréglages')
        except discord.HTTPException as exc:
            audit('role_presets_partial', {'created': created, 'skipped': skipped})
            raise HTTPException(502, f'Création partielle : {len(created)} rôles créés. {exc}')
        created.append({'id': str(role.id), 'name': role.name})
        existing.add(name.casefold())
    audit('role_presets_created', {'created': created, 'skipped': skipped})
    return {'created': created, 'skipped': skipped}

class ChannelsCreate(BaseModel):
    names: str = Field(min_length=1)
    kind: Literal['text', 'voice', 'forum', 'news', 'category'] = 'text'
    category_id: str | None = None
    new_category_name: str | None = Field(default=None, max_length=100)

@app.post('/api/channels')
async def create_channels(payload: ChannelsCreate):
    g = await guild()
    names = [n.strip() for n in payload.names.splitlines() if n.strip()]
    if not names or len(names) > 30:
        raise HTTPException(400, 'Entre 1 et 30 noms par opération')
    if payload.new_category_name and payload.category_id:
        raise HTTPException(400, 'Choisis une catégorie existante OU une nouvelle catégorie')
    if payload.kind == 'category' and (payload.category_id or payload.new_category_name):
        raise HTTPException(400, 'Une catégorie ne peut pas contenir de catégories')
    if payload.kind == 'news' and 'COMMUNITY' not in g.features:
        raise HTTPException(400, 'Les salons annonces nécessitent le mode Communauté')
    cat = None
    if payload.new_category_name is not None:
        new_name = payload.new_category_name.strip()
        if not new_name:
            raise HTTPException(400, 'Nom de nouvelle catégorie vide')
        cat = await g.create_category(new_name, reason='Nebula Core V2.1 : création groupée')
    if payload.category_id:
        cat = g.get_channel(int(payload.category_id))
        if not isinstance(cat, discord.CategoryChannel):
            raise HTTPException(400, 'Catégorie invalide')
    results = []
    for name in names:
        if payload.kind == 'category':
            c = await g.create_category(name, reason='Nebula Core dashboard')
        elif payload.kind == 'voice':
            c = await g.create_voice_channel(name, category=cat, reason='Nebula Core dashboard')
        elif payload.kind == 'forum':
            c = await g.create_forum(name, category=cat, reason='Nebula Core dashboard')
        else:
            c = await g.create_text_channel(name, category=cat, news=(payload.kind == 'news'), reason='Nebula Core dashboard')
        results.append({'id': str(c.id), 'name': c.name})
    audit('channels_created', {'names': [x['name'] for x in results], 'kind': payload.kind})
    return {'created': results, 'category_created': {'id': str(cat.id), 'name': cat.name} if payload.new_category_name and cat else None}

# Explicit tri-state overwrite: allow, deny, inherit.
class PermissionBatch(BaseModel):
    role_id: str
    channel_ids: list[str] = Field(min_length=1, max_length=100)
    permission: Literal['view_channel', 'send_messages', 'read_message_history', 'connect', 'speak', 'manage_messages', 'manage_channels', 'create_public_threads', 'send_messages_in_threads']
    value: Literal['allow', 'deny', 'inherit']

@app.post('/api/permissions/batch')
async def permission_batch(payload: PermissionBatch):
    g = await guild()
    role = g.get_role(int(payload.role_id))
    if not role:
        raise HTTPException(404, 'Rôle introuvable')
    channels = []
    for cid in payload.channel_ids:
        c = g.get_channel(int(cid))
        if c is None:
            raise HTTPException(404, f'Salon introuvable : {cid}')
        channels.append(c)
    value = {'allow': True, 'deny': False, 'inherit': None}[payload.value]
    for c in channels:
        overwrite = c.overwrites_for(role)
        setattr(overwrite, payload.permission, value)
        await c.set_permissions(role, overwrite=overwrite, reason='Nebula Core permissions en masse')
    return {'updated': len(channels)}

class ChannelUpdate(BaseModel):
    channel_id: str
    name: str | None = None
    category_id: str | None = None

@app.post('/api/channels/edit')
async def edit_channel(payload: ChannelUpdate):
    g = await guild()
    c = g.get_channel(int(payload.channel_id))
    if not c:
        raise HTTPException(404, 'Salon introuvable')
    kwargs = {}
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(400, 'Nom vide')
        kwargs['name'] = payload.name.strip()
    if payload.category_id is not None:
        cat = g.get_channel(int(payload.category_id)) if payload.category_id else None
        if cat is not None and not isinstance(cat, discord.CategoryChannel):
            raise HTTPException(400, 'Catégorie invalide')
        if isinstance(c, discord.CategoryChannel):
            raise HTTPException(400, 'Impossible de déplacer une catégorie dans une catégorie')
        kwargs['category'] = cat
    if not kwargs:
        raise HTTPException(400, 'Aucune modification')
    await c.edit(**kwargs, reason='Nebula Core dashboard')
    return {'updated': str(c.id)}

@app.get('/api/backup')
async def backup():
    g = await guild()
    return {
        'guild': {'id': str(g.id), 'name': g.name},
        'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color), 'permissions': r.permissions.value} for r in g.roles],
        'channels': [{'id': str(c.id), 'name': c.name, 'type': str(c.type), 'category_id': str(c.category_id) if getattr(c, 'category_id', None) else None, 'overwrites': {str(target.id): {'allow': allow.value, 'deny': deny.value} for target, (allow, deny) in c.overwrites.items()}} for c in g.channels]
    }

# V2: maintenance endpoints
class RoleUpdate(BaseModel):
    role_id: str
    name: str | None = None
    color: str | None = None
    hoist: bool | None = None
    mentionable: bool | None = None

@app.post('/api/roles/edit')
async def update_role(payload: RoleUpdate):
    g = await guild()
    r = g.get_role(int(payload.role_id))
    if not r or r.is_default() or r.managed:
        raise HTTPException(400, 'Rôle non modifiable')
    changes = {}
    if payload.name is not None:
        if not payload.name.strip(): raise HTTPException(400, 'Nom vide')
        changes['name'] = payload.name.strip()
    if payload.color is not None:
        try: changes['color'] = discord.Color(int(payload.color.lstrip('#'), 16))
        except ValueError: raise HTTPException(400, 'Couleur invalide')
    if payload.hoist is not None: changes['hoist'] = payload.hoist
    if payload.mentionable is not None: changes['mentionable'] = payload.mentionable
    if not changes: raise HTTPException(400, 'Aucun changement')
    await r.edit(**changes, reason='Nebula Core V2')
    audit('role_updated', {'role': r.name, 'changes': list(changes)})
    return {'updated': str(r.id)}

class DeleteItem(BaseModel):
    id: str
    confirmation: str

@app.post('/api/roles/delete')
async def delete_role(payload: DeleteItem):
    g = await guild()
    r = g.get_role(int(payload.id))
    if payload.confirmation != 'SUPPRIMER' or not r or r.is_default() or r.managed:
        raise HTTPException(400, 'Suppression non autorisée')
    await r.delete(reason='Nebula Core V2')
    audit('item_deleted', {'id': payload.id})
    return {'deleted': payload.id}

@app.post('/api/channels/delete')
async def delete_channel(payload: DeleteItem):
    g = await guild()
    c = g.get_channel(int(payload.id))
    if payload.confirmation != 'SUPPRIMER' or not c:
        raise HTTPException(400, 'Suppression non autorisée')
    await c.delete(reason='Nebula Core V2')
    audit('item_deleted', {'id': payload.id})
    return {'deleted': payload.id}

class PermissionMatrix(BaseModel):
    role_ids: list[str] = Field(min_length=1, max_length=20)
    channel_ids: list[str] = Field(min_length=1, max_length=100)
    permissions: dict[str, Literal['allow', 'deny', 'inherit']]

ALLOWED_PERMS = {'view_channel','send_messages','read_message_history','connect','speak','manage_messages','manage_channels','create_public_threads','send_messages_in_threads','attach_files','embed_links','add_reactions','manage_threads','create_private_threads','use_application_commands'}

@app.post('/api/permissions/matrix')
async def permission_matrix(payload: PermissionMatrix):
    g = await guild()
    if not payload.permissions or not set(payload.permissions).issubset(ALLOWED_PERMS):
        raise HTTPException(400, 'Permissions invalides')
    roles = [g.get_role(int(i)) for i in payload.role_ids]
    channels = [g.get_channel(int(i)) for i in payload.channel_ids]
    if any(r is None for r in roles) or any(c is None for c in channels):
        raise HTTPException(404, 'Rôle ou salon introuvable')
    updated = 0
    for c in channels:
        for r in roles:
            overwrite = c.overwrites_for(r)
            for permission, value in payload.permissions.items():
                setattr(overwrite, permission, {'allow': True, 'deny': False, 'inherit': None}[value])
            await c.set_permissions(r, overwrite=overwrite, reason='Nebula Core V2 matrice')
            updated += 1
    audit('permissions_updated', {'roles': len(roles), 'channels': len(channels), 'permissions': payload.permissions})
    return {'updated': updated}

# V2.1: suppressions groupées, avec contrôle serveur strict.
class ChannelsDeleteBatch(BaseModel):
    channel_ids: list[str] = Field(min_length=1, max_length=30)
    confirmation: str

@app.post('/api/channels/delete-batch')
async def delete_channels_batch(payload: ChannelsDeleteBatch):
    g = await guild()
    ids = payload.channel_ids
    if len(ids) != len(set(ids)):
        raise HTTPException(400, 'La sélection contient des doublons')
    if payload.confirmation != f'SUPPRIMER {len(ids)}':
        raise HTTPException(400, 'Confirmation incorrecte')
    channels = []
    for cid in ids:
        try:
            c = g.get_channel(int(cid))
        except ValueError:
            raise HTTPException(400, 'Identifiant de salon invalide')
        if c is None or isinstance(c, discord.CategoryChannel):
            raise HTTPException(400, f'Salon invalide ou catégorie interdite : {cid}')
        channels.append(c)
    deleted, errors = [], []
    for c in channels:
        try:
            await c.delete(reason='Nebula Core V2.1 : suppression groupée')
            deleted.append({'id': str(c.id), 'name': c.name})
        except discord.HTTPException as exc:
            errors.append({'id': str(c.id), 'name': c.name, 'error': str(exc)})
    audit('channels_deleted_batch', {'deleted': deleted, 'errors': errors})
    return {'deleted': deleted, 'errors': errors}

class CategoryDelete(BaseModel):
    category_id: str
    confirmation: str

@app.post('/api/categories/delete-empty')
async def delete_empty_category(payload: CategoryDelete):
    g = await guild()
    if payload.confirmation != 'SUPPRIMER':
        raise HTTPException(400, 'Confirmation incorrecte')
    try:
        c = g.get_channel(int(payload.category_id))
    except ValueError:
        raise HTTPException(400, 'Identifiant de catégorie invalide')
    if not isinstance(c, discord.CategoryChannel):
        raise HTTPException(404, 'Catégorie introuvable')
    if c.channels:
        raise HTTPException(400, 'La catégorie doit être vide avant sa suppression')
    await c.delete(reason='Nebula Core V2.1 : suppression catégorie vide')
    audit('category_deleted', {'name': c.name})
    return {'deleted': str(c.id)}


# Règlement : brouillon et référence au message persistés localement.
RULES_PATH = Path(__file__).parent / 'data' / 'rules.json'
DEFAULT_RULES = "# 📜 RÈGLEMENT — NEBULA\n\nBienvenue sur NEBULA ! Pour garder une communauté agréable, merci de respecter ces règles.\n\n**01 · Respect avant tout**\nAucune insulte ciblée, discrimination, menace, intimidation ou harcèlement. Les désaccords sont permis, les attaques personnelles non.\n\n**02 · Pas de spam ni de publicité sauvage**\nÉvite le flood, les mentions abusives, les liens répétitifs et la promotion sans accord du staff.\n\n**03 · Contenus appropriés**\nPas de contenu pornographique, choquant, illégal ou dangereux. Respecte aussi les règles et conditions de Discord.\n\n**04 · Respect de la vie privée**\nNe partage jamais d'informations personnelles, de conversations privées ou d'images d'autrui sans autorisation.\n\n**05 · Salons et vocaux**\nUtilise les salons selon leur thème. En vocal, laisse chacun s'exprimer et évite les nuisances volontaires.\n\n**06 · Pseudos et profils**\nChoisis un pseudo et un avatar appropriés. L'usurpation d'identité est interdite.\n\n**07 · Modération**\nRespecte les consignes du staff. En cas de problème, contacte la modération calmement plutôt que d'alimenter un conflit.\n\n**08 · Bon sens**\nAucune règle ne remplace le respect et la bienveillance. Le staff peut intervenir face à un comportement nuisible non listé ici.\n\n**En restant sur NEBULA, tu acceptes ce règlement.** ✨"

def load_rules():
    if RULES_PATH.exists():
        try:
            value = json.loads(RULES_PATH.read_text(encoding='utf-8'))
            if isinstance(value, dict):
                return {'content': value.get('content', DEFAULT_RULES),
                        'channel_id': value.get('channel_id'),
                        'message_id': value.get('message_id')}
        except (OSError, ValueError):
            pass
    return {'content': DEFAULT_RULES, 'channel_id': None, 'message_id': None}

def save_rules(value):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RULES_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(RULES_PATH)

class RulesDraft(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

class RulesPublish(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    channel_id: str

@app.get('/api/rules')
async def get_rules():
    await guild()
    value = load_rules()
    return {**value, 'max_length': 2000}

@app.put('/api/rules')
async def put_rules(payload: RulesDraft):
    await guild()
    value = load_rules()
    value['content'] = payload.content
    save_rules(value)
    audit('rules_draft_saved', {'length': len(payload.content)})
    return {'saved': True}

@app.post('/api/rules/publish')
async def publish_rules(payload: RulesPublish):
    g = await guild()
    try:
        channel_id = int(payload.channel_id)
    except ValueError:
        raise HTTPException(400, 'Identifiant de salon invalide')
    channel = g.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        raise HTTPException(400, 'Choisis un salon textuel classique ou un salon d’annonces')
    value = load_rules()
    # Ne jamais modifier un message qui n'appartient pas au bot.
    edited = False
    if value.get('message_id') and str(value.get('channel_id')) == str(channel_id):
        try:
            msg = await channel.fetch_message(int(value['message_id']))
            if msg.author.id != bot.user.id:
                raise HTTPException(409, 'Le message enregistré n’appartient pas à Nebula Core')
            await msg.edit(content=payload.content, allowed_mentions=discord.AllowedMentions.none())
            edited = True
        except discord.NotFound:
            edited = False
    if not edited:
        msg = await channel.send(payload.content, allowed_mentions=discord.AllowedMentions.none())
    value.update({'content': payload.content, 'channel_id': str(channel.id), 'message_id': str(msg.id)})
    save_rules(value)
    audit('rules_published', {'channel_id': str(channel.id), 'message_id': str(msg.id), 'edited': edited})
    return {'published': True, 'edited': edited, 'channel_id': str(channel.id), 'message_id': str(msg.id)}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765)
