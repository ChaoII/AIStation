export default {
  // 页面标题 / 描述
  title: "Síntesis de datos de matrículas",
  sub: "Genera diversas matrículas nacionales (azul / nueva energía / amarilla / de dos pisos / negra / de autobús / de policía), con perturbaciones como perspectiva, rotación, ruido, manchas, oclusión y desenfoque, además de anotaciones de cajas de detección.",

  // 表单
  plateType: "Tipo de matrícula",
  dataset: "Conjunto de datos de destino",
  datasetPlaceholder: "Conjunto de datos donde escribir",
  count: "Cantidad",
  seed: "Semilla aleatoria",
  disturbance: "Perturbaciones",
  closed: "Desactivado",
  restoreDefault: "Restaurar valores predeterminados",
  collapseAll: "Contraer todo",
  expandAll: "Expandir todo",
  disturbHint:
    "Las perturbaciones desactivadas se excluyen de la generación; los parámetros son rangos aleatorios [inferior ~ superior].",
  output: "Salida",
  writeDataset: "Escribir en el conjunto de datos",
  previewOnly: "Solo vista previa",
  writeAnnotation: "Escribir anotación",
  noAnnotation: "Sin anotación",
  start: "Iniciar síntesis",
  tip: "Consejo: cuando no se selecciona ningún conjunto de datos o 'Escribir en el conjunto de datos' está desactivado, solo se muestra una vista previa; después de seleccionar un conjunto de datos y activar la escritura, las imágenes sintetizadas se almacenan y se crea automáticamente una tarea de anotación de detección.",

  // 结果
  resultCount: "Resultados de síntesis ({count})",
  notUploaded: "No escrito (solo vista previa)",
  taskNo: "Tarea #{id}",
  resultAlt: "Matrícula sintetizada",
  savedStore: "Almacenada #{id}",

  // 历史
  historyTitle: "Historial de tareas de síntesis",
  refresh: "Actualizar",
  noJobs: "Aún no hay tareas de síntesis",
  jobId: "ID de la tarea",
  params: "Parámetros",
  total: "Total",
  status: "Estado",
  createdTime: "Hora de creación",

  // 脚本可见文案
  plateTypeBlue: "Azul (turismo)",
  statusCompleted: "Completado",
  statusRunning: "En ejecución",
  statusFailed: "Fallido",
  statusPending: "Pendiente",
  jobParamText: "{count} generadas · {mode}",
  store: "Almacenar",
  preview: "Vista previa",
  generateSuccess: "Síntesis completada, {count} imágenes en total",
  generateFailed: "La síntesis falló",
};
