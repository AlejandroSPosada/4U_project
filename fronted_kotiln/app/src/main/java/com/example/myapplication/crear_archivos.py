from pathlib import Path


def crear_elemento(ruta_str: str):
  """Crea un archivo o una carpeta según la ruta proporcionada."""
  ruta = Path(ruta_str)

  try:
    if ruta.suffix:
      # Crear directorios padres y el archivo
      ruta.parent.mkdir(parents=True, exist_ok=True)
      ruta.touch(exist_ok=True)
      print(f"[Archivo]: {ruta}")
    else:
      # Es una carpeta
      ruta.mkdir(parents=True, exist_ok=True)
      print(f"[Carpeta]: {ruta}")

  except Exception as e:
    print(f"Error al crear '{ruta_str}': {e}")


# Lista con todos los archivos y carpetas que solicitaste

estructura = [
    # Dominio y Modelos
    "domain/model/Alerta.kt",
    
    # Capa de Datos y Repositorios
    "data/repository/AlertasRepository.kt",
    
    # Módulo de Mapas y Lectura MBTiles
    "map/MbtilesReader.kt",
    
    # Componentes de UI Compartidos
    "ui/components/MapaCampus.kt",
    
    # UI y Componentes de Administración del Mapa
    "ui/admin/mapa/EditorMapaScreen.kt",
    "ui/admin/mapa/EditorMapaViewModel.kt",
    "ui/admin/mapa/EditorMapaState.kt",
    "ui/admin/mapa/AlertaFormSheet.kt",
    
    # Activos y Recursos Web
    "assets/map/editor_mapa.html",
]

if __name__ == "__main__":
  print("Creando estructura de archivos y carpetas...\n")
  for elemento in estructura:
    crear_elemento(elemento)
  print("\n¡Estructura creada con éxito!")