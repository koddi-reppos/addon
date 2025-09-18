# -*- coding: utf-8 -*-

import sys, re
PY3 = False
if sys.version_info[0] >= 3: 
    PY3 = True
    unicode = str
    unichr = chr
    long = int
    from urllib.parse import urlparse, parse_qs, quote
else:
    from urlparse import urlparse, parse_qs
    from urllib import quote

from channelselector import get_thumb
from modules import autoplay
from modules import filtertools
from core import httptools
from core import scrapertools
from core import servertools
from core import tmdb
from core.item import Item
from platformcode import config, logger

# Configuración del canal
IDIOMAS = {'Latino': 'lat', 'Español': 'esp', 'Dual': 'dual'}
list_language = list(IDIOMAS.values())
list_quality = ['4K', '1080p', '720p', 'WEB-DL', 'DVDRip', 'BluRay']
list_servers = ['elementum']

canonical = {
    'channel': 'olimpotorrent',
    'host': config.get_setting("current_host", 'olimpotorrent', default=''),
    'host_alt': ["https://olimpotorrent.net", "https://www.olimpotorrent.net", 
                 "https://olimpotorrent.org", "https://olimpotorrent.com"],
    'host_black_list': [],
    'set_tls': True, 
    'set_tls_min': True, 
    'retries_cloudflare': 3,
    'CF': True, 
    'CF_test': False, 
    'alfa_s': True
}

# CORRECCIÓN CRÍTICA: Verificar host válido al inicio
host = canonical['host']
if not host:
    # Probar hosts alternativos
    for test_host in canonical['host_alt']:
        try:
            test_response = httptools.downloadpage(test_host, timeout=5)
            if test_response.sucess:
                host = test_host
                config.set_setting("current_host", host, 'olimpotorrent')
                break
        except:
            continue
    
    # Si no funciona ninguno, usar el primero como fallback
    if not host:
        host = canonical['host_alt'][0]

__channel__ = canonical['channel']
encoding = "utf-8"

def mainlist(item):
    """Menú principal del canal"""
    logger.info()
    
    # CRÍTICO: Inicializar autoplay correctamente
    autoplay.init(item.channel, list_servers, list_quality)
    
    itemlist = []
    
    # Opción principal de películas
    itemlist.append(Item(
        channel=item.channel, 
        title="Películas", 
        action="peliculas", 
        url=host + "/",
        thumbnail=get_thumb("movies", auto=True)
    ))
    
    # Búsqueda
    itemlist.append(Item(
        channel=item.channel, 
        title="Buscar", 
        action="search", 
        thumbnail=get_thumb("search", auto=True)
    ))
    
    # AÑADIDO: Configuración para cambiar hosts
    itemlist.append(Item(
        channel=item.channel, 
        title="Configuración", 
        action="configuracion",
        thumbnail=get_thumb("setting", auto=True)
    ))
    
    # Mostrar opción de autoplay
    autoplay.show_option(item.channel, itemlist)
    
    return itemlist

def newest(categoria):
    """FUNCIÓN CRÍTICA: Esta debe funcionar para que el canal aparezca en Alfa"""
    logger.info("Obteniendo newest para categoria: %s" % categoria)
    
    itemlist = []
    
    try:
        if categoria in ['peliculas', 'latino']:
            # Crear item con todos los parámetros necesarios
            item = Item(
                channel=__channel__,
                action="peliculas",
                url=host + "/"
            )
            
            # Obtener películas
            temp_list = peliculas(item)
            
            # Filtrar solo items válidos para newest
            for movie_item in temp_list:
                if (movie_item.action == "findvideos" and
                    movie_item.contentTitle and 
                    len(movie_item.contentTitle.strip()) > 2 and
                    movie_item.url and
                    'siguiente' not in movie_item.title.lower()):
                    
                    itemlist.append(movie_item)
                    
                    # Limitar a 15 items para newest
                    if len(itemlist) >= 15:
                        break
            
            logger.info("Newest devuelve %d películas válidas" % len(itemlist))
            
    except Exception as e:
        logger.error("Error en newest: %s" % str(e))
        itemlist = []
    
    return itemlist

def search(item, texto):
    """Función de búsqueda"""
    logger.info("Buscando: %s" % texto)
    
    if not texto:
        return []
    
    # Preparar texto de búsqueda
    texto = texto.replace(" ", "+")
    item.url = host + "/?s=" + texto
    
    try:
        # Usar la misma función que peliculas pero con URL de búsqueda
        return peliculas(item)
    except Exception as e:
        logger.error("Error en búsqueda: %s" % str(e))
        return []

def peliculas(item):
    """Función principal para obtener películas"""
    logger.info("Obteniendo películas de: %s" % item.url)
    
    itemlist = []
    
    try:
        # Intentar obtener datos con manejo robusto de errores
        data = None
        current_url = item.url
        
        # Probar con host actual primero
        try:
            response = httptools.downloadpage(current_url, canonical=canonical)
            if response.sucess and response.data:
                data = response.data
        except Exception as e:
            logger.error("Error con URL actual: %s" % str(e))
        
        # Si no funciona, probar hosts alternativos
        if not data:
            global host
            for alt_host in canonical['host_alt']:
                try:
                    alt_url = current_url.replace(host, alt_host)
                    response = httptools.downloadpage(alt_url, canonical=canonical)
                    if response.sucess and response.data:
                        data = response.data
                        host = alt_host
                        config.set_setting("current_host", host, 'olimpotorrent')
                        logger.info("Host cambiado a: %s" % host)
                        break
                except Exception as e:
                    logger.error("Error con host %s: %s" % (alt_host, str(e)))
        
        if not data:
            logger.error("No se pudieron obtener datos de ningún host")
            return []
        
        logger.info("Datos obtenidos correctamente (%d caracteres)" % len(data))
        
        # PATRONES MÚLTIPLES para máxima compatibilidad
        patterns = [
            # WordPress posts con títulos en H1-H6
            r'<h[1-6][^>]*>\s*<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
            # Divs con clases de post/entry/movie
            r'<div[^>]*class=["\'][^"\']*(?:post|entry|movie|torrent)[^"\']*["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
            # Títulos en spans/divs con clase title
            r'<(?:span|div)[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
            # Enlaces con atributo title
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\'][^>]*>',
            # Patrón genérico para cualquier enlace con texto
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]{4,60})</a>'
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, data, re.IGNORECASE | re.DOTALL)
            all_matches.extend(matches)
        
        logger.info("Total de enlaces encontrados: %d" % len(all_matches))
        
        # Procesar enlaces encontrados
        processed_urls = set()  # Evitar duplicados
        
        for url, title in all_matches:
            # Limpiar URL y título
            if not url.startswith('http'):
                if url.startswith('/'):
                    url = host.rstrip('/') + url
                else:
                    url = host.rstrip('/') + '/' + url.lstrip('/')
            
            title = scrapertools.htmlclean(title).strip()
            
            # FILTROS DE CALIDAD para solo películas válidas
            if (url and title and 
                len(title) > 3 and 
                len(title) < 100 and  # Evitar títulos muy largos
                url not in processed_urls and
                is_movie_url(url) and
                not is_navigation_title(title)):
                
                processed_urls.add(url)
                
                # Extraer año si está presente
                year = extract_year(title)
                
                # Crear item de película
                movie_item = Item(
                    channel=item.channel or __channel__,
                    action="findvideos",
                    title=title,
                    contentTitle=clean_title(title),
                    url=url,
                    contentType="movie",
                    thumbnail="",
                    infoLabels={'year': year}
                )
                
                itemlist.append(movie_item)
        
        # Buscar paginación
        pagination_patterns = [
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(?:Siguiente|Next|&gt;|›|»|→)</a>',
            r'<a[^>]*class=["\'][^"\']*next[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
            r'<a[^>]*rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']'
        ]
        
        for pag_pattern in pagination_patterns:
            next_match = re.search(pag_pattern, data, re.IGNORECASE)
            if next_match:
                next_url = next_match.group(1)
                if not next_url.startswith('http'):
                    next_url = host.rstrip('/') + next_url if next_url.startswith('/') else host.rstrip('/') + '/' + next_url
                
                itemlist.append(Item(
                    channel=item.channel or __channel__,
                    action="peliculas",
                    title="Siguiente >>>",
                    url=next_url,
                    thumbnail=get_thumb("next", auto=True)
                ))
                break
        
        logger.info("Películas procesadas: %d" % len([i for i in itemlist if i.action == "findvideos"]))
        
        # Configurar información con TMDB solo si hay resultados
        if itemlist:
            tmdb.set_infoLabels_itemlist(itemlist, True)
        
    except Exception as e:
        logger.error("Error general en peliculas: %s" % str(e))
        import traceback
        logger.error("Traceback: %s" % traceback.format_exc())
    
    return itemlist

def findvideos(item):
    """Buscar enlaces de video (magnets)"""
    logger.info("Buscando videos en: %s" % item.url)
    
    itemlist = []
    
    try:
        # Obtener página del detalle
        response = httptools.downloadpage(item.url, canonical=canonical)
        if not response.sucess or not response.data:
            logger.error("Error obteniendo página de video")
            return []
        
        data = response.data
        logger.info("Página obtenida, buscando magnets...")
        
        # PATRONES EXHAUSTIVOS para magnets
        magnet_patterns = [
            r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^\s<>"\']*',  # Hash hex
            r'magnet:\?xt=urn:btih:[A-Z2-7]{32}[^\s<>"\']*',     # Hash base32
            r'href=["\']?(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"\']*)',
            r'data-[^=]*=["\']?(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"\']*)',
            r'onclick=["\'][^"\']*?(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"\']*)'
        ]
        
        found_magnets = set()
        for pattern in magnet_patterns:
            matches = re.findall(pattern, data, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match[0] else (match[1] if len(match) > 1 else '')
                if match and match.startswith('magnet:'):
                    found_magnets.add(match)
        
        logger.info("Magnets encontrados: %d" % len(found_magnets))
        
        # Procesar cada magnet
        for magnet_url in found_magnets:
            try:
                # Extraer información del magnet
                info = extract_magnet_info(magnet_url)
                
                # Crear título descriptivo
                title_parts = []
                if info['quality']:
                    title_parts.append("[COLOR cyan]%s[/COLOR]" % info['quality'])
                if info['size']:
                    title_parts.append("[COLOR yellow]%s[/COLOR]" % info['size'])
                
                language_name = {v: k for k, v in IDIOMAS.items()}.get(info['language'], 'Latino')
                title_parts.append("[COLOR lime]%s[/COLOR]" % language_name)
                title_parts.append("TORRENT")
                
                title = " ".join(title_parts)
                
                # URL para Elementum
                elementum_url = "plugin://plugin.video.elementum/play?uri=" + quote(magnet_url)
                
                itemlist.append(Item(
                    channel=item.channel,
                    action="play",
                    title=title,
                    url=elementum_url,
                    server="elementum",
                    contentTitle=item.contentTitle,
                    quality=info['quality'],
                    language=info['language'],
                    infoLabels=item.infoLabels
                ))
                
            except Exception as e:
                logger.error("Error procesando magnet: %s" % str(e))
        
        if not itemlist:
            itemlist.append(Item(
                channel=item.channel,
                title="[COLOR red]No se encontraron enlaces magnet[/COLOR]",
                action=""
            ))
        
        # Aplicar filtros
        itemlist = filtertools.get_links(itemlist, item, list_language)
        autoplay.start(itemlist, item)
        
    except Exception as e:
        logger.error("Error en findvideos: %s" % str(e))
        itemlist.append(Item(
            channel=item.channel,
            title="[COLOR red]Error: %s[/COLOR]" % str(e),
            action=""
        ))
    
    return itemlist

def play(item):
    """Reproducir elemento"""
    logger.info()
    item.thumbnail = item.contentThumbnail
    return [item]

def configuracion(item):
    """Configuración del canal"""
    logger.info()
    
    itemlist = []
    
    itemlist.append(Item(
        channel=item.channel,
        title="[COLOR yellow]Hosts disponibles:[/COLOR]",
        action=""
    ))
    
    for alt_host in canonical['host_alt']:
        status = " [COLOR green](Actual)[/COLOR]" if alt_host == host else ""
        itemlist.append(Item(
            channel=item.channel,
            title=alt_host + status,
            action="cambiar_host",
            url=alt_host
        ))
    
    return itemlist

def cambiar_host(item):
    """Cambiar host del canal"""
    logger.info()
    
    global host
    host = item.url
    config.set_setting("current_host", host, 'olimpotorrent')
    
    from platformcode import platformtools
    platformtools.dialog_ok("Olimpotorrent", "Host cambiado a:\n%s" % host)
    
    return []

# FUNCIONES AUXILIARES

def is_movie_url(url):
    """Verificar si es URL de película válida"""
    movie_indicators = ['/pelicula/', '/torrent/', '/descargar/', '/download/', '/ver-']
    avoid_indicators = ['/page/', '/category/', '/tag/', '/author/', '/search/', '/feed/', '.xml', '.rss']
    
    url_lower = url.lower()
    
    # Debe tener al menos un indicador de película
    has_movie_indicator = any(indicator in url_lower for indicator in movie_indicators)
    # No debe tener indicadores a evitar
    has_avoid_indicator = any(indicator in url_lower for indicator in avoid_indicators)
    
    return has_movie_indicator and not has_avoid_indicator

def is_navigation_title(title):
    """Verificar si es título de navegación (no película)"""
    navigation_terms = ['página', 'siguiente', 'anterior', 'home', 'inicio', 'categoría', 
                       'buscar', 'search', 'more', 'ver más', 'página siguiente']
    
    title_lower = title.lower().strip()
    
    # Evitar títulos que son solo años
    if re.match(r'^\d{4}$', title_lower):
        return True
    
    # Evitar títulos de navegación
    return any(term in title_lower for term in navigation_terms)

def extract_year(title):
    """Extraer año del título"""
    year_match = re.search(r'\b(19|20)\d{2}\b', title)
    return year_match.group(0) if year_match else '-'

def clean_title(title):
    """Limpiar título eliminando año y extras"""
    # Eliminar año entre paréntesis o corchetes
    title = re.sub(r'\s*[\[\(]\d{4}[\]\)]\s*', ' ', title)
    # Eliminar calidades
    title = re.sub(r'\s*\b(1080p|720p|4K|BluRay|DVDRip|WEB-DL)\b\s*', ' ', title, flags=re.IGNORECASE)
    # Limpiar espacios múltiples
    title = ' '.join(title.split())
    return title.strip()

def extract_magnet_info(magnet_url):
    """Extraer información del magnet link"""
    info = {
        'filename': 'Torrent',
        'quality': 'SD',
        'language': 'lat',
        'size': ''
    }
    
    try:
        parsed = urlparse(magnet_url)
        query_params = parse_qs(parsed.query)
        filename = query_params.get('dn', [''])[0]
        
        if filename:
            info['filename'] = filename
            
            # Extraer calidad
            filename_upper = filename.upper()
            if '4K' in filename_upper or '2160P' in filename_upper:
                info['quality'] = '4K'
            elif '1080P' in filename_upper:
                info['quality'] = '1080p'
            elif '720P' in filename_upper:
                info['quality'] = '720p'
            elif 'WEB-DL' in filename_upper:
                info['quality'] = 'WEB-DL'
            elif 'BLURAY' in filename_upper:
                info['quality'] = 'BluRay'
            elif 'DVDRIP' in filename_upper:
                info['quality'] = 'DVDRip'
            
            # Extraer idioma
            filename_lower = filename.lower()
            if 'latino' in filename_lower or 'lat' in filename_lower:
                info['language'] = 'lat'
            elif 'español' in filename_lower or 'esp' in filename_lower or 'castellano' in filename_lower:
                info['language'] = 'esp'
            elif 'dual' in filename_lower:
                info['language'] = 'dual'
            
            # Extraer tamaño
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB)', filename, re.IGNORECASE)
            if size_match:
                info['size'] = size_match.group(0)
                
    except Exception as e:
        logger.error("Error extrayendo info de magnet: %s" % str(e))
    
    return info
