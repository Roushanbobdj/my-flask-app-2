importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");

firebase.initializeApp({
  messagingSenderId: "PASTE SENDER ID"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {

self.registration.showNotification(
    payload.notification.title,
    {
        body: payload.notification.body,
        icon: "/static/icons/icon-192.png"
    }
);

});
