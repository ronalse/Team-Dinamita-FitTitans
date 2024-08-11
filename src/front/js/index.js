//import react into the bundle
import React from "react";
import { createRoot } from 'react-dom/client';
//include your index.scss file into the bundle
import "../styles/index.css";

//import your own components
import Layout from "./layout";

// Get the container where the app will be rendered
const container = document.querySelector("#app");

// Create a root using React 18's createRoot
const root = createRoot(container);

// Render the Layout component to the root
root.render(<Layout />);