import asyncio
from redis import Redis
from app.config.settings import settings

async def check_redis():
    print(f"--- Diagnóstico de Redis ---")
    print(f"Intentando conectar a: {settings.REDIS_URL}")
    
    try:
        # Extraer host/puerto/pass para debug (ocultando pass)
        url_preview = settings.REDIS_URL.split('@')[-1] if '@' in settings.REDIS_URL else settings.REDIS_URL
        print(f"Host/Puerto: {url_preview}")
        
        r = Redis.from_url(settings.REDIS_URL, socket_timeout=5)
        is_connected = r.ping()
        
        if is_connected:
            print("✅ ¡EXITO! Conexión a Redis establecida correctamente.")
        else:
            print("❌ Redis respondió pero no de forma esperada (Ping fallido).")
            
    except Exception as e:
        print(f"❌ ERROR de conexión: {str(e)}")
        print("\nConsejos:")
        print("1. Verifica que la variable REDIS_URL sea correcta en Railway.")
        print("2. Si Railway usa REDISURL, asegúrate de haberla mapeado en Settings.")
        print("3. Si estás probando desde local a Railway, asegúrate de que el servicio sea accesible externamente o usa el 'Public Domain' de Redis.")

if __name__ == "__main__":
    asyncio.run(check_redis())
