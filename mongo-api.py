from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient, DESCENDING
from datetime import datetime
from bson import ObjectId

app = FastAPI()

# CORS manual via middleware
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = JSONResponse(content={}, status_code=200)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

client = MongoClient("mongodb://ISIS2304D21202610:uglfhwtSyjrx@157.253.236.88:8087/")
db  = client["ISIS2304D21202610"]
col = db["resenias"]

def serial(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    if "fecha" in doc and isinstance(doc["fecha"], datetime):
        doc["fecha"] = doc["fecha"].isoformat()
    if "respuesta_admin" in doc and doc["respuesta_admin"]:
        if "fecha" in doc["respuesta_admin"]:
            doc["respuesta_admin"]["fecha"] = doc["respuesta_admin"]["fecha"].isoformat()
    if "votos_utiles" in doc:
        for v in doc["votos_utiles"]:
            if "fecha" in v and isinstance(v["fecha"], datetime):
                v["fecha"] = v["fecha"].isoformat()
    return doc

@app.get("/")
def inicio():
    return {"estado": "API Dann-Alpes funcionando correctamente"}

@app.post("/resenas")
def crear_resena(datos: dict):
    reserva_id = datos.get("reserva_id")
    if col.find_one({"reserva_id": reserva_id}):
        raise HTTPException(status_code=400, detail="Ya existe una reseña para esta reserva")
    doc = {
        "hotel_id":    int(datos.get("hotel_id")),
        "cliente_id":  int(datos.get("cliente_id")),
        "reserva_id":  int(reserva_id),
        "calificacion": int(datos.get("calificacion")),
        "comentario":  datos.get("comentario"),
        "fecha":       datetime.now(),
        "estado":      "PUBLICADA",
        "utilidad":    0,
        "destacada":   False,
        "votos_utiles":    [],
        "respuesta_admin": None
    }
    result = col.insert_one(doc)
    return {"mensaje": "Reseña creada", "id": str(result.inserted_id)}

@app.put("/resenas/{resena_id}")
def editar_resena(resena_id: str, datos: dict):
    result = col.update_one(
        {"_id": ObjectId(resena_id), "estado": "PUBLICADA"},
        {"$set": {
            "calificacion": int(datos.get("calificacion")),
            "comentario":   datos.get("comentario"),
            "fecha_modificacion": datetime.now()
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada o ya eliminada")
    return {"mensaje": "Reseña actualizada"}

@app.delete("/resenas/{resena_id}")
def eliminar_resena(resena_id: str):
    result = col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {"estado": "ELIMINADA"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    return {"mensaje": "Reseña eliminada"}

@app.get("/hoteles/{hotel_id}/resenas")
def get_resenas_hotel(hotel_id: int, orden: str = "fecha", pagina: int = 1, por_pagina: int = 10):
    campo = "fecha" if orden == "fecha" else "utilidad"
    skip  = (pagina - 1) * por_pagina
    destacada = col.find_one({"hotel_id": hotel_id, "estado": "PUBLICADA", "destacada": True})
    cursor = col.find(
        {"hotel_id": hotel_id, "estado": "PUBLICADA", "destacada": {"$ne": True}}
    ).sort(campo, DESCENDING).skip(skip).limit(por_pagina)
    resenas = [serial(r) for r in cursor]
    if destacada and pagina == 1:
        resenas.insert(0, serial(destacada))
    total = col.count_documents({"hotel_id": hotel_id, "estado": "PUBLICADA"})
    return {"total": total, "pagina": pagina, "resenas": resenas}

@app.post("/resenas/{resena_id}/votos")
def votar_resena(resena_id: str, datos: dict):
    cliente_id = int(datos.get("cliente_id"))
    if col.find_one({"_id": ObjectId(resena_id), "votos_utiles.usuario_id": cliente_id}):
        raise HTTPException(status_code=400, detail="Ya votaste esta reseña")
    result = col.update_one(
        {"_id": ObjectId(resena_id), "estado": "PUBLICADA"},
        {
            "$push": {"votos_utiles": {"usuario_id": cliente_id, "fecha": datetime.now()}},
            "$inc":  {"utilidad": 1}
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    return {"mensaje": "Voto registrado"}

@app.get("/clientes/{cliente_id}/resenas")
def historial_cliente(cliente_id: int, orden: str = "fecha"):
    campo = "fecha" if orden == "fecha" else "hotel_id"
    cursor = col.find({"cliente_id": cliente_id}).sort(campo, DESCENDING)
    return [serial(r) for r in cursor]

@app.post("/resenas/{resena_id}/respuesta")
def responder_resena(resena_id: str, datos: dict):
    result = col.update_one(
        {"_id": ObjectId(resena_id), "estado": "PUBLICADA"},
        {"$set": {
            "respuesta_admin": {
                "admin_id": int(datos.get("admin_id")),
                "texto":    datos.get("texto"),
                "fecha":    datetime.now()
            }
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    return {"mensaje": "Respuesta publicada"}

@app.delete("/resenas/{resena_id}/admin")
def eliminar_resena_admin(resena_id: str):
    result = col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {"estado": "ELIMINADA"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    return {"mensaje": "Reseña eliminada por administrador"}

@app.put("/resenas/{resena_id}/destacar")
def destacar_resena(resena_id: str, datos: dict):
    hotel_id = int(datos.get("hotel_id"))
    col.update_many({"hotel_id": hotel_id, "destacada": True}, {"$set": {"destacada": False}})
    result = col.update_one(
        {"_id": ObjectId(resena_id), "estado": "PUBLICADA"},
        {"$set": {"destacada": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    return {"mensaje": "Reseña destacada"}

@app.get("/analytics/top-hoteles")
def top_hoteles(anio: int = 2024):
    pipeline = [
        {"$match": {
            "estado": "PUBLICADA",
            "fecha": {"$gte": datetime(anio,1,1), "$lte": datetime(anio,12,31,23,59,59)}
        }},
        {"$group": {
            "_id": "$hotel_id",
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"calificacion_promedio": -1}},
        {"$limit": 10},
        {"$project": {
            "_id": 0,
            "hotel_id": "$_id",
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "total_resenas": 1
        }}
    ]
    return list(col.aggregate(pipeline))

@app.get("/analytics/evolucion/{hotel_id}")
def evolucion_hotel(hotel_id: int, anio: int = 2024):
    pipeline = [
        {"$match": {
            "hotel_id": hotel_id,
            "estado": "PUBLICADA",
            "fecha": {"$gte": datetime(anio,1,1), "$lte": datetime(anio,12,31,23,59,59)}
        }},
        {"$group": {
            "_id": {"mes": {"$month": "$fecha"}},
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"_id.mes": 1}},
        {"$project": {
            "_id": 0,
            "mes": "$_id.mes",
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "total_resenas": 1
        }}
    ]
    return list(col.aggregate(pipeline))

@app.get("/analytics/comparativo")
def comparativo_ciudad(hotel_ids: str):
    ids = [int(x) for x in hotel_ids.split(",")]
    pipeline = [
        {"$match": {"hotel_id": {"$in": ids}, "estado": "PUBLICADA"}},
        {"$group": {
            "_id": "$hotel_id",
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas":         {"$sum": 1},
            "con_respuesta": {"$sum": {"$cond": [{"$ifNull": ["$respuesta_admin", False]}, 1, 0]}},
            "destacadas":    {"$sum": {"$cond": ["$destacada", 1, 0]}}
        }},
        {"$addFields": {
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "pct_con_respuesta": {"$round": [{"$multiply": [{"$divide": ["$con_respuesta", "$total_resenas"]}, 100]}, 1]},
            "pct_destacadas":    {"$round": [{"$multiply": [{"$divide": ["$destacadas", "$total_resenas"]}, 100]}, 1]}
        }},
        {"$sort": {"calificacion_promedio": -1}},
        {"$project": {
            "_id": 0,
            "hotel_id": "$_id",
            "calificacion_promedio": 1,
            "total_resenas": 1,
            "pct_con_respuesta": 1,
            "pct_destacadas": 1
        }}
    ]
    resultados = list(col.aggregate(pipeline))
    if not resultados:
        return []
    promedio_ciudad = round(sum(r["calificacion_promedio"] for r in resultados) / len(resultados), 2)
    for r in resultados:
        r["bajo_promedio_ciudad"] = r["calificacion_promedio"] < promedio_ciudad
    return {"promedio_ciudad": promedio_ciudad, "hoteles": resultados}