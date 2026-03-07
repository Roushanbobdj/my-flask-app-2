importScripts("https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyCJE_ERiqvNNAzIkz03w7rfV5eBHue7Mi0",
  projectId: "library-notification-df69f",
  messagingSenderId: "618545934932",
  appId: "1:618545934932:web:5a1f2e240abd3c7398b3c1"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {

 self.registration.showNotification(payload.notification.title,{
   body: payload.notification.body
 });

});
