/** Catppuccin Mocha palette — mirrors the PC app's color scheme. */
export const C = {
  bg:      '#1e1e2e',
  surface: '#313244',
  card:    '#181825',
  cardAlt: '#45475a',
  text:    '#cdd6f4',
  subtext: '#a6adc8',
  muted:   '#6c7086',
  accent:  '#89b4fa',
  border:  '#45475a',
  green:   '#a6e3a1',
  yellow:  '#f9e2af',
  red:     '#f38ba8',
  mauve:   '#cba6f7',
  teal:    '#89dceb',
};

/** Role → accent color (matches BUILTIN_ROLES colors in storage/roles.py). */
export const MODE_COLORS: Record<string, string> = {
  negotiator:     C.mauve,
  teacher:        C.teal,
  health_coach:   C.green,
  psychologist:   C.mauve,
  language_tutor: C.teal,
  topic_learning: C.yellow,
};

/** Role → display emoji. */
export const MODE_ICONS: Record<string, string> = {
  negotiator:     '🤝',
  teacher:        '📚',
  health_coach:   '🏃',
  psychologist:   '🧠',
  language_tutor: '🌍',
  topic_learning: '💡',
};
