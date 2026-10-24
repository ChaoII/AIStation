export default {
  // 页面标题 / 描述
  title: "Kennzeichendaten-Synthese",
  sub: "Verschiedene inländische Kennzeichen generieren (blau / neue Energie / gelb / doppelstöckig / schwarz / Bus / Polizei), mit Störungen wie Perspektive, Rotation, Rauschen, Flecken, Verdeckung und Unschärfe, plus Bounding-Box-Annotationen.",

  // 表单
  plateType: "Kennzeichentyp",
  dataset: "Ziel-Datensatz",
  datasetPlaceholder: "Datensatz, in den geschrieben wird",
  count: "Anzahl",
  seed: "Zufalls-Seed",
  disturbance: "Störungen",
  closed: "Deaktiviert",
  restoreDefault: "Standard wiederherstellen",
  collapseAll: "Alle einklappen",
  expandAll: "Alle ausklappen",
  disturbHint:
    "Deaktivierte Störungen sind von der Generierung ausgeschlossen; Parameter sind Zufallsbereiche [unterer ~ oberer Wert].",
  output: "Ausgabe",
  writeDataset: "In Datensatz schreiben",
  previewOnly: "Nur Vorschau",
  writeAnnotation: "Annotation schreiben",
  noAnnotation: "Keine Annotation",
  start: "Synthese starten",
  tip: "Hinweis: Wenn kein Datensatz ausgewählt ist oder 'In Datensatz schreiben' deaktiviert ist, wird nur eine Vorschau angezeigt; nach Auswahl eines Datensatzes und Aktivieren des Schreibens werden die synthetisierten Bilder gespeichert und automatisch eine Erkennungs-Annotation-Aufgabe erstellt.",

  // 结果
  resultCount: "Synthesevergebnisse ({count})",
  notUploaded: "Nicht geschrieben (nur Vorschau)",
  taskNo: "Aufgabe #{id}",
  resultAlt: "Synthetisiertes Kennzeichen",
  savedStore: "Gespeichert #{id}",

  // 历史
  historyTitle: "Verlauf der Syntheseaufgaben",
  refresh: "Aktualisieren",
  noJobs: "Noch keine Syntheseaufgaben",
  jobId: "Aufgaben-ID",
  params: "Parameter",
  total: "Gesamt",
  status: "Status",
  createdTime: "Erstellt am",

  // 脚本可见文案
  plateTypeBlue: "Blau (Pkw)",
  statusCompleted: "Abgeschlossen",
  statusRunning: "Läuft",
  statusFailed: "Fehlgeschlagen",
  statusPending: "Ausstehend",
  jobParamText: "{count} generiert · {mode}",
  store: "Speichern",
  preview: "Vorschau",
  generateSuccess: "Synthese abgeschlossen, insgesamt {count} Bilder",
  generateFailed: "Synthese fehlgeschlagen",
};
