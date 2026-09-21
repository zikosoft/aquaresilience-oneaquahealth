// Vuetify's type declarations reference the global JSX namespace (for render
// function typings) even though this project never authors JSX. `vue`
// ships this exact declaration at `vue/jsx.d.ts`, but that subpath isn't
// exposed through vue's package.json `exports` map under "Bundler" module
// resolution, so it can't be pulled in via a `reference types` directive.
// Inlining the same declaration (copied from vue/jsx.d.ts) keeps this in
// sync with what Vue itself provides for JSX-authoring consumers.
import type { NativeElements, ReservedProps, VNode } from 'vue'

declare global {
  namespace JSX {
    export interface Element extends VNode {}
    export interface ElementClass {
      $props: object
    }
    export interface ElementAttributesProperty {
      $props: object
    }
    export interface IntrinsicElements extends NativeElements {
      [name: string]: any
    }
    export interface IntrinsicAttributes extends ReservedProps {}
  }
}
