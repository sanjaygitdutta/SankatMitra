importScripts("https://www.gstatic.com/firebasejs/9.0.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/9.0.0/firebase-messaging-compat.js");

firebase.initializeApp({
    apiKey: "YOUR_FIREBASE_API_KEY_HERE",
    authDomain: "sankatmitraa.firebaseapp.com",
    projectId: "sankatmitraa",
    storageBucket: "sankatmitraa.firebasestorage.app",
    messagingSenderId: "832297728694",
    appId: "1:832297728694:web:74b8328407dcd8137a0417",
    measurementId: "G-B812WGSQ1X"
});

const messaging = firebase.messaging();

// Optional: Handle background messages
messaging.onBackgroundMessage((payload) => {
    console.log('[firebase-messaging-sw.js] Received background message ', payload);
    const notificationTitle = payload.notification.title;
    const notificationOptions = {
        body: payload.notification.body,
        icon: '/icons/Icon-192.png'
    };

    self.registration.showNotification(notificationTitle, notificationOptions);
});
