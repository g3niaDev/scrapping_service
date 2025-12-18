import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000/v1"

async def main():
    print("🚀 Iniciando Test de Research Companion...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Check Health (implied by connection)
        try:
            resp = await client.get("http://localhost:8000/health")
            if resp.status_code != 200:
                print("❌ Error: API no responde en /health")
                return
            print("✅ API Online")
        except Exception as e:
             print(f"❌ Error conectando a la API: {e}")
             print("   -> Asegúrate de ejecutar: uvicorn app.main:app --host 0.0.0.0 --port 8000")
             return

        # 2. Create Session
        print("\n1️⃣  Creando Sesión...")
        session_payload = {
            "event_id": "evt_123",
            "initial_message": "Quiero investigar sobre Deepmind"
        }
        resp = await client.post(f"{BASE_URL}/interviews/sessions", json=session_payload)
        if resp.status_code != 201:
            print(f"❌ Falla al crear sesión: {resp.text}")
            return
        
        data = resp.json()
        session_id = data["id"]
        print(f"✅ Sesión creada ID: {session_id}")
        print(f"   Estado: {data['state']}")
        print(f"   Mensaje Sistema: {data['messages'][-1]['content']}")

        # 3. Simulate User Interaction (Disambiguation)
        # Assuming the logic asks for Topic confirmation or Company
        if data['state'] == 'collecting':
             print("\n2️⃣  Enviando 'Es una empresa'...")
             resp = await client.post(f"{BASE_URL}/interviews/sessions/{session_id}/messages", json={"content": "Es una empresa"})
             data = resp.json()
             print(f"   Respuesta: {data['messages'][-1]['content']}")

        # 4. Confirming
        print("\n3️⃣  Confirmando información 'Si'...")
        resp = await client.post(f"{BASE_URL}/interviews/sessions/{session_id}/messages", json={"content": "Si"})
        data = resp.json()
        print(f"✅ Estado actual: {data['state']} (Esperado: researching)")

        if data['state'] == 'researching':
            print("\n4️⃣  Investigación iniciada en background (Celery).")
            print("   -> Revisa la consola de Celery para ver el job ejecutándose.")
            print("   -> Puedes consultar el job status en unos segundos.")

    print("\n🎉 Test completado.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
