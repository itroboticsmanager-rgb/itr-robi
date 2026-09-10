import { element } from './icons.js';
import './banners.css';

// Вбудованих банерів кіоск не має: показує лише те, що школа опублікувала
// для стійки в CRM. Тут лишається тільки ілюстрація для банера з CRM без
// власної картинки (або з картинкою, що не завантажилась).
//
// Local vector artwork only. No markup from banner feeds is interpolated here.
const art = `<svg viewBox="0 0 640 400" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="340" cy="337" rx="210" ry="24" fill="var(--art-shadow)"/>
    <path d="M102 326H555" stroke="var(--art-line)" stroke-width="2"/>
    <g fill="var(--art-blue)"><rect x="122" y="290" width="168" height="35" rx="12"/><rect x="158" y="262" width="96" height="39" rx="12"/></g>
    <path d="M139 318H273" stroke="var(--art-deep)" stroke-width="7" stroke-linecap="round"/>
    <g class="arm-assembly" data-motion="arm">
      <path d="M205 275L258 170" stroke="var(--art-deep)" stroke-width="59" stroke-linecap="round"/>
      <path d="M205 267L253 173" stroke="var(--art-blue)" stroke-width="42" stroke-linecap="round"/>
      <g class="arm-forearm" data-motion="forearm">
        <path d="M258 170L403 136" stroke="var(--art-deep)" stroke-width="49" stroke-linecap="round"/>
        <path d="M263 160L401 127" stroke="var(--art-blue)" stroke-width="32" stroke-linecap="round"/>
        <g class="arm-gripper" data-motion="gripper">
          <rect x="391" y="133" width="24" height="41" rx="9" fill="var(--art-deep)"/>
          <path d="M382 180V166H423V180" fill="none" stroke="var(--art-white)" stroke-width="12" stroke-linejoin="round"/>
          <path d="M378 175V190M428 175V190" stroke="var(--art-deep)" stroke-width="8" stroke-linecap="round"/>
          <path d="M378 194L402 180L429 194L404 210Z" fill="var(--art-yellow)"/>
          <path d="M378 194V221L404 237V210Z" fill="var(--art-gold)"/>
          <path d="M404 210L429 194V221L404 237Z" fill="var(--art-yellow)"/>
        </g>
        <circle cx="403" cy="135" r="18" fill="var(--art-white)"/><circle cx="403" cy="135" r="8" fill="var(--art-blue)"/>
      </g>
      <circle cx="258" cy="170" r="30" fill="var(--art-yellow)"/><circle cx="258" cy="170" r="13" fill="var(--art-gold)"/>
    </g>
    <circle cx="205" cy="272" r="22" fill="var(--art-white)"/><circle cx="205" cy="272" r="10" fill="var(--art-blue)"/>
    <g stroke="var(--art-blue)" stroke-width="2" fill="none" opacity=".35"><path d="M365 305V272L416 243L469 272V305L416 335Z M365 272L416 303L469 272 M416 303V335"/></g>
    <path d="M476 214H521V153" fill="none" stroke="var(--art-line)" stroke-width="3" stroke-linecap="round"/>
    <circle class="arm-signal" data-motion="signal" cx="521" cy="143" r="8" fill="var(--art-blue)"/>
  </svg>`;

export function createBannerArt() {
  const node = element('div', 'banner-motion banner-motion-robotics');
  node.setAttribute('aria-hidden', 'true');
  const svg = new DOMParser().parseFromString(art, 'image/svg+xml').documentElement;
  node.append(document.importNode(svg, true));
  return node;
}
