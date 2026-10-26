export default {
  // 页面标题 / 描述
  title: "Synthèse de plaques d'immatriculation",
  sub: "Génère diverses plaques d'immatriculation nationales (bleue / énergie nouvelle / jaune / à deux étages / noire / autocar / police), avec des perturbations telles que la perspective, la rotation, le bruit, les taches, l'occlusion et le flou, plus des annotations de boîtes de détection.",

  // 表单
  plateType: "Type de plaque",
  dataset: "Jeu de données cible",
  datasetPlaceholder: "Jeu de données vers lequel écrire",
  count: "Nombre",
  seed: "Graine aléatoire",
  disturbance: "Perturbations",
  closed: "Désactivé",
  restoreDefault: "Restaurer les valeurs par défaut",
  collapseAll: "Tout réduire",
  expandAll: "Tout déplier",
  disturbHint:
    "Les perturbations désactivées sont exclues de la génération ; les paramètres sont des plages aléatoires [inférieure ~ supérieure].",
  output: "Sortie",
  writeDataset: "Écrire dans le jeu de données",
  previewOnly: "Aperçu uniquement",
  writeAnnotation: "Écrire l'annotation",
  noAnnotation: "Aucune annotation",
  start: "Démarrer la synthèse",
  tip: "Astuce : lorsqu'aucun jeu de données n'est sélectionné ou que « Écrire dans le jeu de données » est désactivé, seul un aperçu est affiché ; après avoir sélectionné un jeu de données et activé l'écriture, les images synthétisées sont stockées et une tâche d'annotation de détection est créée automatiquement.",

  // 结果
  resultCount: "Résultats de la synthèse ({count})",
  notUploaded: "Non écrit (aperçu uniquement)",
  taskNo: "Tâche #{id}",
  resultAlt: "Plaque synthétisée",
  savedStore: "Stocké #{id}",

  // 历史
  historyTitle: "Historique des tâches de synthèse",
  refresh: "Actualiser",
  noJobs: "Aucune tâche de synthèse pour l'instant",
  jobId: "ID de la tâche",
  params: "Paramètres",
  total: "Total",
  status: "Statut",
  createdTime: "Heure de création",

  // 脚本可见文案
  plateTypeBlue: "Bleue (voiture de tourisme)",
  statusCompleted: "Terminé",
  statusRunning: "En cours",
  statusFailed: "Échec",
  statusPending: "En attente",
  jobParamText: "{count} généré(s) · {mode}",
  store: "Stocker",
  preview: "Aperçu",
  generateSuccess: "Synthèse terminée, {count} images au total",
  generateFailed: "Échec de la synthèse",
};
