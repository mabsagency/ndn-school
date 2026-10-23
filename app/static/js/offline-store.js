(function () {
  const DB_NAME = "ndn-offline-v1";
  const STORE_NAME = "snapshots";
  const ITERATIONS = 310000;
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();

  function openDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME, { keyPath: "username" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function deriveKey(password, salt) {
    const source = await crypto.subtle.importKey(
      "raw", textEncoder.encode(password), "PBKDF2", false, ["deriveKey"]
    );
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
      source,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function save(snapshot, password) {
    if (!window.crypto?.subtle || !window.indexedDB) {
      throw new Error("Stockage chiffré indisponible sur ce navigateur.");
    }
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(password, salt);
    const plaintext = textEncoder.encode(JSON.stringify(snapshot));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
    const database = await openDatabase();
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put({
        username: snapshot.username.toLocaleLowerCase("fr"),
        salt,
        iv,
        ciphertext,
        savedAt: new Date().toISOString(),
        version: 1,
      });
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
    database.close();
  }

  async function get(username) {
    const database = await openDatabase();
    const record = await new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, "readonly")
        .objectStore(STORE_NAME).get(username.trim().toLocaleLowerCase("fr"));
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
    database.close();
    return record;
  }

  async function unlock(record, password) {
    const key = await deriveKey(password, record.salt);
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: record.iv }, key, record.ciphertext
    );
    return { snapshot: JSON.parse(textDecoder.decode(plaintext)), savedAt: record.savedAt };
  }

  async function remove(username) {
    const database = await openDatabase();
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(username.trim().toLocaleLowerCase("fr"));
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
    database.close();
  }

  window.NdnOfflineStore = { get, remove, save, unlock };
})();
