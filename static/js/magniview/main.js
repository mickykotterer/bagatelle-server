// import './main.css';
import { createMagniviewHTML } from './js/createMagniview.js';
import { cacheControls, loadImages} from './js/variable.js';
import { addEventListeners } from './js/events.js';

export function initializeMagniview() {
   loadImages();
   createMagniviewHTML();
   cacheControls();
   addEventListeners();
}
