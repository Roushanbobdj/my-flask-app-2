importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyBgNcTolAC58hxkPhwzUUkXf63vJ7ZREdI",
  authDomain: "roushan-reading-room.firebaseapp.com",
  projectId: "roushan-reading-room",
  storageBucket: "roushan-reading-room.firebasestorage.app",
  messagingSenderId: "483049478376",
  appId: "1:483049478376:web:577fc54d967d53318f515d"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {

  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: "/static/icons/icon-192.png"
  };

  self.registration.showNotification(notificationTitle, notificationOptions);

});
