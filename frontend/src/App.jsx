import { Routes, Route } from "react-router-dom";

import Header from "./components/Header.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import AboutPage from "./pages/AboutPage.jsx";

export default function App() {
  return (
    <div className="app">
      <Header />
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<ChatPage />} />
      </Routes>
    </div>
  );
}
