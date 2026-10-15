<!-- 首页品牌标题：采用现代宋体的字形、比例及青蓝强调线，与正文无衬线字体独立。 -->
<template>
  <h2 class="river-heading">心有山海，<br />自有<span>知舟。</span></h2>
</template>
<style scoped>
.river-heading {
  min-height: 157px;
  margin: 18px 0 16px;
  color: var(--text);
  font-family: 'Noto Serif CJK SC', 'Source Han Serif SC', 'Songti SC', STSong, SimSun, serif;
  font-size: clamp(54px, 5.2vw, 74px);
  font-weight: 700;
  letter-spacing: 4px;
  line-height: 1.12;
}
.river-heading span {
  color: var(--brand);
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, var(--brand) 30%, transparent);
  text-decoration-thickness: 4px;
  text-underline-offset: 10px;
}
@media (max-width: 760px) {
  .river-heading {
    min-height: 113px;
    margin-top: 22px;
    font-size: 49px;
    letter-spacing: 0;
  }
}
</style>
