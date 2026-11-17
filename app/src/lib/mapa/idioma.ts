// Textos de los controles de MapLibre en español (AC-G1). Son aria-label y title: los leen los lectores de
// pantalla y aparecen al pasar el mouse. Se traduce el diccionario completo de MapLibre 6, no solo los
// controles que se usan hoy, para que un control nuevo no aparezca en inglés.
export const LOCALE_MAPA: Record<string, string> = {
	'AttributionControl.ToggleAttribution': 'Mostrar u ocultar la atribución',
	'AttributionControl.MapFeedback': 'Comentarios sobre el mapa',
	'CooperativeGesturesHandler.WindowsHelpText': 'Usá Ctrl + rueda del mouse para acercar el mapa',
	'CooperativeGesturesHandler.MacHelpText': 'Usá ⌘ + rueda del mouse para acercar el mapa',
	'CooperativeGesturesHandler.MobileHelpText': 'Usá dos dedos para mover el mapa',
	'FullscreenControl.Enter': 'Pantalla completa',
	'FullscreenControl.Exit': 'Salir de pantalla completa',
	'GeolocateControl.FindMyLocation': 'Buscar mi ubicación',
	'GeolocateControl.LocationNotAvailable': 'Ubicación no disponible',
	'GlobeControl.Enable': 'Ver como globo',
	'GlobeControl.Disable': 'Ver como plano',
	'LogoControl.Title': 'Logo de MapLibre',
	'Map.Title': 'Mapa',
	'Marker.Title': 'Marcador',
	'NavigationControl.ResetBearing': 'Arrastrá para girar el mapa; hacé clic para volver al norte',
	'NavigationControl.ZoomIn': 'Acercar',
	'NavigationControl.ZoomOut': 'Alejar',
	'Popup.Close': 'Cerrar',
	'ScaleControl.Feet': 'pies',
	'ScaleControl.Meters': 'm',
	'ScaleControl.Kilometers': 'km',
	'ScaleControl.Miles': 'mi',
	'ScaleControl.NauticalMiles': 'mn',
	'TerrainControl.Enable': 'Activar relieve',
	'TerrainControl.Disable': 'Desactivar relieve'
};
