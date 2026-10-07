/** A typed coverage-only planning step; Python validates all draft references. */
import {Type} from '@earendil-works/pi-ai';
export function coverageParameters() {
  const text=()=>Type.String({minLength:1});
  const level=Type.Union(['unit','integration','e2e'].map(x=>Type.Literal(x)));
  const ref=Type.Object({task:text(),criterion:text()});
  return Type.Object({coverage_plan:Type.Object({
    strategy:Type.Object({unit:text(),integration:text(),e2e:text()}),
    checks:Type.Array(Type.Object({task:text(),criterion:text(),level,
      test:Type.Integer({minimum:0}),oracle:text()}),{minItems:1}),
    requirements:Type.Array(Type.Object({requirement:text(),cases:Type.Array(ref,{minItems:1})}),{minItems:1}),
    gaps:Type.Array(Type.Object({task:text(),case:Type.Object({id:text(),given:text(),when:text(),then:text()}),
      level,test:Type.Array(text(),{minItems:1}),reason:text()}))
  })});
}
