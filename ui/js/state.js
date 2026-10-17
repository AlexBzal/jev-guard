// Estado compartido y bus de eventos entre vistas.

const bus = new EventTarget();

export const store = {
  health: null,
  policy: null,
  scenarios: [],
  pendingCount: 0,
  labAction: null, // acción que otra vista pide abrir en el Laboratorio
};

export function emit(type, detail) {
  bus.dispatchEvent(new CustomEvent(type, { detail }));
}

/** Suscribe y devuelve la función para desuscribir. */
export function on(type, fn) {
  const handler = (e) => fn(e.detail);
  bus.addEventListener(type, handler);
  return () => bus.removeEventListener(type, handler);
}

export function questionFor(actionType, qid) {
  const list = store.policy?.questions?.[actionType] || [];
  return list.find((q) => q.qid === qid);
}

export function tierPolicy(tier) {
  return store.policy?.policy?.tiers?.[tier];
}
